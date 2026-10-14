"""Local-only data preparation and provenance. Never downloads data."""
import copy
import hashlib
import json
from pathlib import Path

from .schema import CHECKS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding='utf-8-sig') as f:
        for line_no, line in enumerate(f, 1):
            if line.strip():
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError('Expected a JSON object')
                    rows.append(value)
                except (ValueError, TypeError) as e:
                    raise ValueError(f'{path}:{line_no}: {e}') from e
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')


def validate_pair(row):
    for key in ('id', 'english', 'gloss', 'source_group'):
        if not isinstance(row.get(key), str) or (key != 'gloss' and not row[key].strip()):
            raise ValueError(f'Pair requires string {key}; only gloss may be empty')
    provenance = row.get('provenance')
    if not isinstance(provenance, dict) or not provenance.get('kind') or not provenance.get('version'):
        raise ValueError('provenance requires kind and version')
    if row.get('split') not in (None, 'dev', 'test'):
        raise ValueError('split must be dev or test')
    if row.get('cohort', 'unreviewed_reference') not in ('controlled', 'reviewed_reference', 'unreviewed_reference', 'natural', 'synthetic_reference'):
        raise ValueError('Invalid cohort')
    if row.get('cohort') == 'reviewed_reference' and not row.get('review', {}).get('reviewer'):
        raise ValueError('Reviewed references require reviewer metadata')
    if 'reference_gloss' in row and not isinstance(row['reference_gloss'], str):
        raise ValueError('reference_gloss must be a string')
    if any(k not in CHECKS or v not in ('MATCH', 'MISMATCH', 'UNKNOWN') for k, v in row.get('expected', {}).items()):
        raise ValueError('Invalid expected check labels')
    if row.get('error_type') and row['error_type'] not in CHECKS:
        raise ValueError('Invalid error_type')
    if row.get('audit', {}).get('cause') not in (None, 'english_extraction', 'gloss_extraction', 'normalization', 'comparison', 'unresolved'):
        raise ValueError('Invalid audit cause')
    return row


def prepare(rows, seed='signir-2026', test_fraction=0.3):
    """Connected components prevent document/duplicate/variant chain leakage."""
    if not 0 < test_fraction < 1:
        raise ValueError('test_fraction must lie strictly between zero and one')
    rows = copy.deepcopy(rows)
    ids = {}
    for i, row in enumerate(rows):
        validate_pair(row)
        if row['id'] in ids:
            raise ValueError('Duplicate pair ID: ' + row['id'])
        ids[row['id']] = i
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        parent[find(i)] = find(j)
    seen = {}
    for i, row in enumerate(rows):
        keys = [('source', row['source_group']),
                ('english', ' '.join(row['english'].casefold().split()))]
        if row.get('document_id'):
            keys.append(('document', row.get('corpus', ''), row['document_id']))
        if row.get('duplicate_group'):
            keys.append(('duplicate', row['duplicate_group']))
        # A shared missing parent ID still links variants; an existing parent
        # is linked directly, even if it has changed wording or provenance.
        if row.get('variant_of'):
            keys.append(('family', row['variant_of']))
            if row['variant_of'] in ids:
                union(i, ids[row['variant_of']])
        for key in keys:
            if key in seen:
                union(i, seen[key])
            seen[key] = i
    groups = {}
    for i in range(len(rows)):
        groups.setdefault(find(i), []).append(i)
    for indices in groups.values():
        names = sorted(rows[i]['id'] for i in indices)
        group = digest(names)[:20]
        requested = {rows[i]['split'] for i in indices if rows[i].get('split')}
        if len(requested) > 1:
            raise ValueError('Leakage: one connected group has conflicting dev/test assignments')
        split = next(iter(requested)) if requested else ('test' if int(digest([seed, names])[:16], 16) / 16**16 < test_fraction else 'dev')
        for i in indices:
            rows[i].update(split=split, split_group=group, preparation={'version': '1', 'seed': seed, 'test_fraction': test_fraction})
    return sorted(rows, key=lambda r: r['id'])


def import_prior(predictions, corpus, manifest):
    run_id = manifest.get('run_id')
    if not run_id:
        raise ValueError('Prior manifest requires run_id')
    lookup = {}
    for item in corpus:
        lookup.setdefault((item['text'], item['gloss']), []).append(item)
    rows = []
    for p in predictions:
        matches = lookup.get((p['source'], p['reference']), [])
        if len(matches) != 1 or not matches[0].get('doc_id'):
            raise ValueError('Source/reference join is missing, ambiguous, or lacks doc_id; supply an explicit reviewed mapping')
        c = matches[0]
        identity = [run_id, c['doc_id'], c.get('sent_idx'), p['source'], p['reference']]
        rows.append({'id': run_id + ':' + digest(identity)[:20], 'english': p['source'],
                     'gloss': p['hypothesis'], 'reference_gloss': p['reference'],
                     'document_id': c['doc_id'], 'source_group': c['doc_id'],
                     'corpus': c.get('source', 'asllrp'), 'cohort': 'natural',
                     'provenance': {'kind': 'saved_generated', 'version': run_id,
                                    'generator': manifest.get('config', {}).get('llm'),
                                    'prompt_hash': manifest.get('gloss_prompt_hash'),
                                    'manifest_hash': digest(manifest), 'corpus_sent_idx': c.get('sent_idx')},
                     'review': {'status': 'unreviewed'}})
    for row in rows:
        validate_pair(row)
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate predictions after join')
    return rows
