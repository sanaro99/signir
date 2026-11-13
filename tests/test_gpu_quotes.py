"""Protocol version 2: the model quotes its evidence and code finds the offsets."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPARK = ROOT / 'experiments/dgx-spark'
PAIR = {'id': 'a', 'english': 'Alice buys 3 apples.', 'gloss': 'fs-ALICE BUY 9 APPLE', 'source_group': 'doc'}


def quoted(response_text):
    """Rewrite a version-1 response (offset spans) as a version-2 response (quotes)."""
    payload = json.loads(response_text)
    for item in (payload.get('facts') or payload.get('checks')).values():
        for key in [k for k in item if k.endswith('evidence')]:
            item[key] = [span['text'] for span in item[key]]
    return json.dumps(payload)


def without_positions(value):
    if isinstance(value, dict):
        return {k: without_positions(v) for k, v in value.items() if k not in ('start', 'end')}
    return [without_positions(v) for v in value] if isinstance(value, list) else value


class QuoteProtocolTests(unittest.TestCase):
    def test_quotes_become_exact_spans(self):
        from signir.gpu.protocol import locate_quotes
        text = 'Alice buys 3 apples.'
        self.assertEqual(locate_quotes(['Alice', 'apples'], text),
                         [{'start': 0, 'end': 5, 'text': 'Alice'}, {'start': 13, 'end': 19, 'text': 'apples'}])
        for span in locate_quotes(['é', '🙂 b'], 'café 🙂 b'):
            self.assertEqual('café 🙂 b'[span['start']:span['end']], span['text'])

    def test_repeated_quotes_take_successive_occurrences(self):
        # Stated rule: a quote names its first occurrence; quoting it again names the next one.
        from signir.gpu.protocol import locate_quotes
        spans = locate_quotes(['BUY', 'BUY'], 'BUY APPLE BUY')
        self.assertEqual([(s['start'], s['end']) for s in spans], [(0, 3), (10, 13)])
        with self.assertRaisesRegex(ValueError, 'not in the unchanged'):
            locate_quotes(['BUY', 'BUY', 'BUY'], 'BUY APPLE BUY')

    def test_ungrounded_or_malformed_quotes_are_failures_never_repaired(self):
        from signir.gpu.protocol import locate_quotes
        for quotes in (['pear'], ['Alice  buys'], ['alice'], [''], [5], 'Alice', None,
                       [{'start': 0, 'end': 5, 'text': 'Alice'}]):
            with self.subTest(quotes=quotes), self.assertRaises(ValueError):
                locate_quotes(quotes, 'Alice buys 3 apples')

    def test_version_2_requests_ask_for_quotes_and_leave_version_1_alone(self):
        from signir.gpu.protocol import make_request
        for task in ('english', 'gloss', 'judge'):
            old, new = make_request(task, PAIR), make_request(task, PAIR, 2)
            self.assertEqual(old, make_request(task, PAIR, 1))
            self.assertEqual(old['messages'][1], new['messages'][1])
            self.assertNotEqual(old['messages'][0], new['messages'][0])
            self.assertIn('"start"', json.dumps(old['schema']))
            self.assertNotIn('"start"', json.dumps(new['schema']))
            prompt = ' '.join(new['messages'][0]['content'].split('Return only JSON')[0].split())
            self.assertIn('Do not write character offsets', prompt)
            self.assertNotIn('offset', prompt.replace('Do not write character offsets', ''))

    def test_config_versions(self):
        from signir.gpu.protocol import default_config, validate_config
        self.assertEqual(default_config()['version'], 1)
        validate_config({**default_config(), 'version': 2})
        with self.assertRaises(ValueError):
            validate_config({**default_config(), 'version': 3})
        base = json.loads((SPARK / 'config.json').read_text(encoding='utf-8'))
        for name, batch in (('config-quotes.json', 4), ('config-quotes-serial.json', 1)):
            config = validate_config(json.loads((SPARK / name).read_text(encoding='utf-8')))
            # Only the evidence mechanism (and, for the smoke, concurrency) differs from version 1.
            self.assertEqual({**config, 'version': 1, 'batch_size': 4}, base)
            self.assertEqual((config['version'], config['batch_size']), (2, batch))

    def test_freeze_fingerprints_the_version_2_prompts(self):
        from signir.gpu.storage import sources
        names = {name.replace('\\', '/') for name in sources()}
        self.assertLessEqual({'gpu/prompts/english.txt', 'gpu/prompts/v2/english.txt',
                              'gpu/prompts/v2/gloss.txt', 'gpu/prompts/v2/judge.txt'}, names)

    def test_version_2_replay_matches_version_1_and_records_bad_quotes_as_failures(self):
        from signir.gpu.backend import ReplayBackend
        from signir.gpu.protocol import default_config
        from signir.gpu.runner import run_experiment
        from signir.gpu.storage import freeze_experiment, read_json
        saved = [json.loads(line) for line in
                 (SPARK / 'fixtures/responses.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        pairs = SPARK / 'fixtures/pairs.jsonl'

        def run(root, name, version, rows):
            responses = root / (name + '.jsonl')
            responses.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
            frozen = freeze_experiment(pairs, {**default_config(), 'version': version}, 'a' * 40, 'replay')
            run_experiment(pairs, frozen, root / name, ReplayBackend(responses))
            records = [json.loads(line) for line in
                       (root / name / 'records.jsonl').read_text(encoding='utf-8').splitlines()]
            return records, read_json(root / name / 'manifest.json')

        def as_quotes(rows):
            return [{**row, 'response': {**row['response'], 'text': quoted(row['response']['text'])}} for row in rows]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, first_manifest = run(root, 'v1', 1, saved)
            second, second_manifest = run(root, 'v2', 2, as_quotes(saved))
            self.assertEqual(first_manifest['failed_requests'], 0)
            self.assertEqual(second_manifest['failed_requests'], 0)
            # Same facts and statuses. Positions may differ only where a quote occurs twice
            # (the stated first-occurrence rule), and every span still indexes the text.
            self.assertEqual(without_positions([row['arms'] for row in first]),
                             without_positions([row['arms'] for row in second]))
            for row in second:
                for side in ('english', 'gloss'):
                    for fact in row['arms']['structured'][side]['record']['facts'].values():
                        for span in fact['evidence']:
                            self.assertEqual(row[side][span['start']:span['end']], span['text'])
            # A version-1 response is not a valid version-2 response: nothing is converted silently.
            _, mixed = run(root, 'mixed', 2, saved)
            self.assertEqual(mixed['failed_requests'], mixed['requests'])
            # One invented quote fails that reading; the pair's extraction arm stays UNKNOWN.
            broken = as_quotes(saved)
            broken[0]['response']['text'] = broken[0]['response']['text'].replace('"Alice"', '"Alicia"', 1)
            records, manifest = run(root, 'broken', 2, broken)
            self.assertGreaterEqual(manifest['failed_requests'], 1)
            failed = [row for row in records if row['arms']['structured']['status'] == 'error']
            self.assertTrue(failed)
            self.assertIn('not in the unchanged', failed[0]['arms']['structured']['english']['error'])
            self.assertEqual({c['status'] for c in failed[0]['arms']['structured']['checks'].values()}, {'UNKNOWN'})


class EngineFailureTests(unittest.TestCase):
    def test_engine_failure_stops_the_run_and_is_not_cached(self):
        # A dead engine (out of memory, CUDA fault) says nothing about a request. Caching it
        # as that request's answer would make a resumed run keep the failure forever.
        from signir.gpu.runner import cached_generate
        calls = []

        def generate(requests):
            calls.append(len(requests))
            if len(calls) == 2:
                raise RuntimeError('CUDA out of memory')
            return [{'text': '{}', 'finish_reason': 'stop'} for _ in requests]
        backend = SimpleNamespace(identity={'kind': 'cuda-vllm'}, generate=generate)
        requests = [{'task': 'english', 'n': n} for n in range(10)]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'out of memory'):
                cached_generate(requests, {'freeze_id': 'a'}, directory, backend, 4)
            self.assertEqual(calls, [4, 4])
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 4)
            # Resuming generates only what was never answered.
            calls.clear()
            backend.generate = lambda batch: calls.append(len(batch)) or [
                {'text': '{}', 'finish_reason': 'stop'} for _ in batch]
            self.assertEqual(len(cached_generate(requests, {'freeze_id': 'a'}, directory, backend, 4)), 10)
            self.assertEqual(calls, [4, 2])

    def test_one_rejected_input_is_still_isolated_from_its_neighbours(self):
        from signir.gpu.runner import cached_generate

        def generate(requests):
            if any(request['n'] == 2 for request in requests):
                raise ValueError('rejected input')
            return [{'text': '{}', 'finish_reason': 'stop'} for _ in requests]
        backend = SimpleNamespace(identity={'kind': 'cuda-vllm'}, generate=generate)
        requests = [{'task': 'english', 'n': n} for n in range(4)]
        with tempfile.TemporaryDirectory() as directory:
            results = cached_generate(requests, {'freeze_id': 'a'}, directory, backend, 4)
        self.assertEqual([r['finish_reason'] for r in results], ['stop', 'stop', 'error', 'stop'])


if __name__ == '__main__':
    unittest.main()
