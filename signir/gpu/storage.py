"""Immutable experiment fingerprints, input validation, and safe file writes."""
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, distributions, requires, version
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
from urllib.request import urlopen

from .protocol import PROMPTS, validate_config


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode('utf-8')).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                prefix='.pending-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        # Same-directory hard link atomically publishes only a completed file.
        # Unlike replace(), it cannot overwrite an existing freeze/cache entry.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_pairs(path):
    rows, ids, partitions = [], set(), {}
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key].strip()
                for key in ('id', 'english', 'gloss', 'source_group')):
            raise ValueError(f'Line {number}: require nonempty id, english, gloss, source_group strings')
        if row['id'] in ids:
            raise ValueError('Duplicate pair ID')
        split = row.get('split', 'diagnostic')
        if split not in ('dev', 'test', 'diagnostic'):
            raise ValueError('Split must be dev, test or diagnostic')
        # Protect explicit document/family IDs and source duplicates across splits.
        for key in (('document', row['source_group']),
                    ('english', ' '.join(row['english'].casefold().split())),
                    ('family', row.get('family_id', row['source_group']))):
            if key in partitions and partitions[key] != split:
                raise ValueError('Related examples or identical English cross splits')
            partitions[key] = split
        ids.add(row['id'])
        rows.append(row)
    if not rows:
        raise ValueError('Input must contain at least one pair')
    return rows


def sources():
    root = Path(__file__).parents[1]
    paths = sorted(root.rglob('*.py')) + sorted(PROMPTS.glob('*.txt'))
    return {str(path.relative_to(root)): file_hash(path) for path in paths}


def dependencies():
    result = {}
    for name in ('spacy', 'lemminflect', 'en_core_web_sm', 'torch', 'vllm', 'transformers'):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = None
    from ..natural import extraction_configuration
    result['extraction'] = extraction_configuration()
    result['python'] = platform.python_version()
    result['installed_distributions'] = {
        re.sub(r'[-_.]+', '-', item.metadata['Name']).lower(): item.version
        for item in distributions() if item.metadata['Name']}
    cpu, pending = {}, ['spacy', 'lemminflect', 'en-core-web-sm']
    while pending:
        name = re.sub(r'[-_.]+', '-', pending.pop()).lower()
        if name in cpu:
            continue
        try:
            cpu[name] = version(name)
            requirements = requires(name) or []
        except PackageNotFoundError:
            cpu[name] = None
            continue
        if requirements:
            from packaging.requirements import Requirement
            for requirement in map(Requirement, requirements):
                if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                    pending.append(requirement.name)
    result['cpu_dependencies'] = cpu
    return result


def resolve_revision(model):
    with urlopen('https://huggingface.co/api/models/' + model, timeout=30) as response:
        revision = json.load(response)['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Model registry did not return an immutable commit SHA')
    return revision


def freeze_experiment(input_path, config, revision, image):
    validate_config(config)
    pairs = load_pairs(input_path)
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Model/tokenizer revision must be an immutable 40-character commit SHA')
    if image != 'replay' and not re.fullmatch(r'[\w./:-]+@sha256:[0-9a-f]{64}', image):
        raise ValueError('Actual inference requires an immutable container image digest')
    try:
        git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
            cwd=Path(__file__).parents[2], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        git_head = None
    result = {'version': 1, 'input_sha256': file_hash(input_path), 'pairs': len(pairs),
              'config': config, 'model_revision': revision, 'tokenizer_revision': revision,
              'container_image': image, 'source_sha256': sources(),
              'dependencies': dependencies(), 'git_head': git_head,
              'created_utc': datetime.now(timezone.utc).isoformat()}
    result['freeze_id'] = digest(result)
    return result


def verify_freeze(input_path, frozen, dependency_mode='all'):
    content = {k: v for k, v in frozen.items() if k != 'freeze_id'}
    if frozen.get('version') != 1 or digest(content) != frozen.get('freeze_id'):
        raise ValueError('Invalid or edited experiment freeze')
    validate_config(frozen['config'])
    if file_hash(input_path) != frozen['input_sha256'] or sources() != frozen['source_sha256']:
        raise ValueError('Input, code or prompts changed since freeze; create a new experiment')
    current, expected = dependencies(), frozen['dependencies']
    if dependency_mode == 'cpu':
        keys = ('python', 'spacy', 'lemminflect', 'en_core_web_sm', 'extraction', 'cpu_dependencies')
        current, expected = ({key: item[key] for key in keys} for item in (current, expected))
    elif dependency_mode != 'all':
        raise ValueError('Dependency verification mode must be all or cpu')
    if current != expected:
        raise ValueError('Runtime dependencies changed since freeze')
    return load_pairs(input_path)


def protect_output(output, inputs):
    output = Path(output).resolve()
    for source in inputs:
        source = Path(source).resolve()
        if (source == output or output in source.parents
                or output.exists() and source.exists() and output.samefile(source)):
            raise ValueError('Output would overwrite or contain a protected input')
    return output
