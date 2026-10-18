"""CPU planning audit; optional exact frozen-tokenizer profiling, no model load."""
from collections import Counter
import json
from pathlib import Path
import re
import time

from ..compare import check_pair
from ..schema import CHECKS
from .protocol import compare_records, default_config, make_request, validate_config
from .storage import digest, file_hash, load_pairs, protect_output, resolve_revision, write_json


def audit(input_path, output, config=None, tokenizer=None, revision=None, protected=()):
    config = validate_config(config or default_config())
    pairs = load_pairs(input_path)
    output = protect_output(output, [input_path, *protected])
    if output.exists() and any(output.iterdir()):
        raise ValueError('Dry-run output must be new or empty')
    requests = {digest(request): request for pair in pairs
                for request in (make_request(task, pair) for task in ('english','gloss','judge'))}
    profiles = []
    for key, request in requests.items():
        profile = {'request_sha256': key, 'task': request['task'],
            'prompt_characters': sum(len(message['content']) for message in request['messages']),
            'prompt_tokens': None, 'fits_context_with_output_reserve': None}
        if tokenizer is not None:
            ids = tokenizer.apply_chat_template(request['messages'], tokenize=True,
                add_generation_prompt=True, enable_thinking=False)
            tokens = len(ids['input_ids'] if isinstance(ids, dict) else ids)
            profile.update(prompt_tokens=tokens,
                fits_context_with_output_reserve=tokens + config['max_tokens'] <= config['max_model_len'])
        profiles.append(profile)
    start, baseline = time.perf_counter(), []
    for pair in pairs:
        result = check_pair(pair['english'], pair['gloss'])
        baseline.append({'id':pair['id'], 'checks':compare_records(result['english'],result['gloss'])})
    seconds = time.perf_counter()-start
    result = {'kind':'cpu-planning-audit','model_loaded':False,'cuda_executed':False,
        'input_sha256':file_hash(input_path), 'pairs':len(pairs),
        'unique_english':len({pair['english'] for pair in pairs}),
        'unique_gloss':len({pair['gloss'] for pair in pairs}),
        'total_requests':3*len(pairs), 'unique_requests':len(requests),
        'duplicate_requests_saved':3*len(pairs)-len(requests),
        'requests_by_task':dict(Counter(item['task'] for item in profiles)),
        'phenomena':dict(Counter(pair.get('phenomenon','unspecified') for pair in pairs)),
        'cpu_baseline_seconds':seconds, 'model':config['model'], 'model_revision':revision,
        'exact_tokenizer_used':tokenizer is not None, 'config':config, 'request_profiles':profiles,
        'baseline_assessed_checks':sum(check['status']!='UNKNOWN' for row in baseline for check in row['checks'].values()),
        'baseline_possible_supported_checks':len(pairs)*4,
        'over_budget_requests':sum(item['fits_context_with_output_reserve'] is False for item in profiles) if tokenizer is not None else None,
        'limits':['CPU planning cannot establish CUDA compatibility or GPU throughput.',
                  'Character counts are exact lengths, not token estimates.',
                  'Exact token budgets require the pinned tokenizer; no model weights are loaded.']}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'audit.json', result)
    with (output/'baseline.jsonl').open('x',encoding='utf-8') as handle:
        for row in baseline:
            handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    return result


def load_tokenizer(config, revision=None):
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise ValueError('Exact token profiling requires Transformers; install it separately or use the vLLM container') from exc
    revision = revision or resolve_revision(config['model'])
    if not re.fullmatch(r'[0-9a-f]{40}',revision):
        raise ValueError('Tokenizer profiling requires an immutable commit SHA')
    tokenizer = AutoTokenizer.from_pretrained(config['model'], revision=revision, trust_remote_code=False)
    return tokenizer, revision
