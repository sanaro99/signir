"""Three-arm experiment execution with immutable requests and resumable cache."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from ..compare import check_pair
from ..schema import CHECKS
from .protocol import compare_records, make_request, parse_extraction, parse_judge
from .storage import digest, protect_output, read_json, verify_freeze, write_json


def cached_generate(requests, frozen, cache, backend, batch_size):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    keys, pending, results = [], {}, {}
    for request in requests:
        key = digest({'freeze_id': frozen['freeze_id'], 'backend': backend.identity, 'request': request})
        keys.append(key)
        path = cache / (key + '.json')
        if path.exists():
            item = read_json(path)
            if (item.get('key') != key or item.get('request') != request
                    or item.get('response_sha256') != digest(item.get('response'))):
                raise ValueError('Cached response/request was modified')
            results[key] = item['response']
        else:
            pending[key] = request
    entries = list(pending.items())
    backend.last_cache_stats = {'total_requests': len(requests), 'unique_requests': len(set(keys)),
        'cached_unique_requests': len(results), 'new_unique_requests': len(entries), 'validation_splits': 0}
    if entries and hasattr(backend, 'prepare'):
        # Imports, CUDA kernels and model loading are setup, not predictions.
        backend.prepare()
    def generate_isolated(batch):
        try:
            outputs = backend.generate([request for _, request in batch])
            if len(outputs) != len(batch):
                raise ValueError('Backend returned the wrong number of outputs')
            return outputs
        except ValueError as exc:
            # vLLM can reject a batch for one bad input before generation.
            # Isolate that input rather than permanently failing its neighbors.
            if len(batch) > 1:
                backend.last_cache_stats['validation_splits'] += 1
                middle = len(batch) // 2
                return generate_isolated(batch[:middle]) + generate_isolated(batch[middle:])
            return [{'text': '', 'finish_reason': 'error', 'error': type(exc).__name__ + ': ' + str(exc)}]
        except Exception as exc:
            return [{'text': '', 'finish_reason': 'error',
                     'error': type(exc).__name__ + ': ' + str(exc)} for _ in batch]
    for offset in range(0, len(entries), batch_size):
        batch = entries[offset:offset + batch_size]
        outputs = generate_isolated(batch)
        for (key, request), output in zip(batch, outputs):
            write_json(cache / (key + '.json'), {'key': key, 'freeze_id': frozen['freeze_id'],
                'request': request, 'response': output, 'response_sha256': digest(output)})
            results[key] = output
        print(f'Cached {min(offset + batch_size, len(entries))}/{len(entries)} new requests', file=sys.stderr)
    return [results[key] for key in keys]


def interpret_response(task, pair, response):
    try:
        if response.get('error'):
            raise ValueError(response['error'])
        if response.get('finish_reason') != 'stop':
            raise ValueError('Incomplete generation: ' + str(response.get('finish_reason')))
        payload = json.loads(response['text'])
        if task == 'judge':
            parsed = parse_judge(payload, pair['english'], pair['gloss'])
        else:
            parsed = parse_extraction(payload, pair[task], task)
        return {'status': 'ok', 'record': parsed, 'error': None}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'status': 'error', 'record': None, 'error': type(exc).__name__ + ': ' + str(exc)}


def unknown_checks(reason):
    return {name: {'status': 'UNKNOWN', 'reason': reason,
            'english_evidence': [], 'gloss_evidence': []} for name in CHECKS}


def replace_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    temporary.replace(path)


def run_experiment(input_path, frozen, output, backend, protected=()):
    mode = 'cpu' if backend.identity['kind'] == 'replay' else 'all'
    pairs = verify_freeze(input_path, frozen, dependency_mode=mode)
    output = protect_output(output, [input_path, *protected])
    files = ('manifest.json', 'manifest.json.tmp', 'records.jsonl', 'records.jsonl.tmp',
             'summary.json', 'summary.json.tmp', 'checks.csv')
    files += ('analysis.json', 'analysis.json.tmp', 'report.md', 'review_queue.jsonl')
    for name in files:
        protect_output(output / name, [input_path, *protected])
    manifest_path = output / 'manifest.json'
    if output.exists() and any(output.iterdir()) and not manifest_path.exists():
        raise ValueError('Output is not an existing matching experiment or an empty directory')
    manifest = {'version': 1, 'freeze_id': frozen['freeze_id'], 'backend': backend.identity,
                'cuda_inference': False,
                'status': 'running', 'pairs': len(pairs),
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'limits': ['Replay is software validation, not model evidence.',
                           'Coverage is not accuracy; reviewed annotations are required.',
                           'Roles and unsupported event alignment remain UNKNOWN.']}
    if manifest_path.exists():
        old = read_json(manifest_path)
        if old['freeze_id'] != frozen['freeze_id'] or old['backend'] != backend.identity:
            raise ValueError('Output belongs to a different frozen experiment/backend')
        manifest['created_utc'] = old['created_utc']
        manifest['previous_attempts'] = old.get('previous_attempts',[]) + [{key:old.get(key)
            for key in ('status','completed_utc','attempt_wall_seconds','cache_stats','backend_metrics')}]
        replace_json(manifest_path, manifest)
    else:
        write_json(manifest_path, manifest)
    try:
        start = time.perf_counter()
        records = execute(pairs, frozen, output, backend, manifest, manifest_path)
        from .evaluation import evaluate, write_reports
        summary = evaluate(records)
        summary['provenance'] = {'freeze_id': frozen['freeze_id'],
            'backend': backend.identity['kind'], 'input_sha256': frozen['input_sha256']}
        write_reports(output, records, summary)
        manifest['status'] = 'complete_with_errors' if manifest['failed_requests'] else 'complete'
        manifest['attempt_wall_seconds'] = time.perf_counter() - start
        manifest['backend_metrics'] = getattr(backend, 'metrics', None)
        manifest['cache_stats'] = backend.last_cache_stats
        manifest['cuda_inference'] = (backend.identity['kind']=='cuda-vllm'
            and bool(getattr(backend,'metrics',{}).get('batches')))
        replace_json(manifest_path, manifest)
        return records
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=type(exc).__name__ + ': ' + str(exc),
                        completed_utc=datetime.now(timezone.utc).isoformat())
        manifest['attempt_wall_seconds'] = time.perf_counter() - start
        manifest['backend_metrics'] = getattr(backend, 'metrics', None)
        manifest['cache_stats'] = getattr(backend, 'last_cache_stats', None)
        manifest['cuda_inference'] = (backend.identity['kind']=='cuda-vllm'
            and bool(getattr(backend,'metrics',{}).get('batches')))
        replace_json(manifest_path, manifest)
        raise


def execute(pairs, frozen, output, backend, manifest, manifest_path):
    # Setup errors must stop the experiment, not become semantic UNKNOWNs.
    baseline_start = time.perf_counter()
    baseline = [check_pair(pair['english'], pair['gloss']) for pair in pairs]
    manifest['cpu_baseline_seconds'] = time.perf_counter() - baseline_start
    requests = [make_request(task, pair) for pair in pairs for task in ('english', 'gloss', 'judge')]
    responses = cached_generate(requests, frozen, output / 'cache', backend, frozen['config']['batch_size'])
    records, failures = [], 0
    for index, (pair, cpu) in enumerate(zip(pairs, baseline)):
        a, b, judge = [interpret_response(task, pair, responses[3*index + j])
                       for j, task in enumerate(('english', 'gloss', 'judge'))]
        checks = (compare_records(a['record'], b['record']) if a['status'] == b['status'] == 'ok'
                  else unknown_checks('Extraction failed; see recorded error and raw cached response'))
        status = 'ok' if a['status'] == b['status'] == 'ok' else 'error'
        failures += sum(item['status'] == 'error' for item in (a, b, judge))
        records.append({'id': pair['id'], 'source_group': pair['source_group'],
            'phenomenon': pair.get('phenomenon'), 'family_id': pair.get('family_id'),
            'split': pair.get('split', 'diagnostic'), 'english': pair['english'], 'gloss': pair['gloss'],
            'arms': {'cpu': {'status': 'ok', 'english': cpu['english'], 'gloss': cpu['gloss'],
                             'checks': compare_records(cpu['english'], cpu['gloss'])},
                     'structured': {'status': status, 'english': a, 'gloss': b, 'checks': checks},
                     'judge': {'status': judge['status'], 'error': judge['error'],
                               'checks': judge['record'] if judge['status'] == 'ok'
                               else unknown_checks('Direct judgment failed; see error and raw cached response')}}})
    temporary = output / 'records.jsonl.tmp'
    with temporary.open('w', encoding='utf-8') as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(output / 'records.jsonl')
    manifest.update(status='inference_complete', failed_requests=failures,
                    completed_utc=datetime.now(timezone.utc).isoformat(),
                    requests=len(requests), unique_cached_requests=len(list((output / 'cache').glob('*.json'))))
    cached = [read_json(path)['response'] for path in (output / 'cache').glob('*.json')]
    manifest['cached_token_usage'] = {key: sum(item.get(key, 0) for item in cached)
                                    for key in ('prompt_tokens', 'completion_tokens')}
    replace_json(manifest_path, manifest)
    return records
