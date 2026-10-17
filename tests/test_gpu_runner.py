import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from signir.schema import record


class GPURunnerTests(unittest.TestCase):
    def test_model_setup_failure_is_fatal_before_any_request_is_cached(self):
        from signir.gpu.runner import cached_generate
        with tempfile.TemporaryDirectory() as directory:
            def fail_setup():
                raise RuntimeError('model initialization failed')
            backend = SimpleNamespace(identity={'kind': 'cuda-vllm'}, prepare=fail_setup,
                generate=lambda requests: self.fail('A failed model must never generate'))
            with self.assertRaisesRegex(RuntimeError, 'initialization'):
                cached_generate([{'task': 'english'}], {'freeze_id': 'a'}, directory, backend, 1)
            self.assertEqual(list(Path(directory).glob('*.json')), [])

    def test_replay_rejects_changed_cpu_dependencies(self):
        from signir.gpu.protocol import default_config
        from signir.gpu.storage import freeze_experiment, verify_freeze
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.jsonl'
            path.write_text('{"id":"a","english":"a","gloss":"A","source_group":"doc"}\n')
            frozen = freeze_experiment(path, default_config(), 'a' * 40, 'replay')
            changed = copy.deepcopy(frozen['dependencies'])
            changed['spacy'] = 'different-version'
            with patch('signir.gpu.storage.dependencies', return_value=changed), self.assertRaises(ValueError):
                verify_freeze(path, frozen, dependency_mode='cpu')

    def test_failed_baseline_updates_manifest_instead_of_leaving_running(self):
        from signir.gpu.backend import ReplayBackend
        from signir.gpu.protocol import default_config
        from signir.gpu.runner import run_experiment
        from signir.gpu.storage import freeze_experiment, read_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'input.jsonl'
            path.write_text('{"id":"a","english":"a","gloss":"A","source_group":"doc"}\n')
            responses = root / 'responses.jsonl'
            responses.write_text('')
            frozen = freeze_experiment(path, default_config(), 'a' * 40, 'replay')
            with patch('signir.gpu.runner.check_pair', side_effect=ValueError('missing English model')):
                with self.assertRaises(ValueError):
                    run_experiment(path, frozen, root / 'run', ReplayBackend(responses))
            self.assertEqual(read_json(root / 'run/manifest.json')['status'], 'failed')

    def test_summary_temporary_alias_cannot_overwrite_input(self):
        from signir.gpu.backend import ReplayBackend
        from signir.gpu.protocol import default_config
        from signir.gpu.runner import run_experiment
        from signir.gpu.storage import freeze_experiment
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'input.jsonl'
            source = '{"id":"a","english":"Alice buys 3 apples.","gloss":"fs-ALICE BUY 3 APPLE","source_group":"doc"}\n'
            path.write_text(source)
            responses = root / 'responses.jsonl'
            responses.write_text('')
            frozen = freeze_experiment(path, default_config(), 'a' * 40, 'replay')
            out = root / 'run'
            backend = ReplayBackend(responses)
            run_experiment(path, frozen, out, backend)
            (out / 'summary.json.tmp').symlink_to(path)
            with self.assertRaises(ValueError):
                run_experiment(path, frozen, out, backend)
            self.assertEqual(path.read_text(), source)

    def test_interrupted_cache_write_does_not_publish_partial_json(self):
        from signir.gpu.storage import write_json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.json'
            def interrupt(value, handle, **kwargs):
                handle.write('{"partial":')
                raise KeyboardInterrupt()
            with patch('signir.gpu.storage.json.dump', side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    write_json(path, {'value': 1})
            self.assertFalse(path.exists())
            write_json(path, {'value': 2})
            self.assertEqual(json.loads(path.read_text()), {'value': 2})

    def test_freeze_records_transitive_dependency_inventory(self):
        from signir.gpu.storage import dependencies
        frozen_dependencies = dependencies()
        self.assertIn('installed_distributions', frozen_dependencies)
        self.assertIn('cpu_dependencies', frozen_dependencies)
        # packaging is a transitive dependency of spaCy in the installed natural environment.
        if frozen_dependencies['spacy']:
            self.assertIn('packaging', frozen_dependencies['cpu_dependencies'])

    def test_cuda_is_required_even_when_torch_can_import(self):
        from signir.gpu.backend import cuda_preflight
        fake = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict('sys.modules', {'torch': fake}), self.assertRaisesRegex(RuntimeError, 'CUDA'):
            cuda_preflight()

    def test_replay_runs_all_arms_and_resumes_without_regenerating(self):
        from signir.gpu.backend import ReplayBackend
        from signir.gpu.runner import run_experiment
        from signir.gpu.protocol import default_config
        from signir.gpu.storage import freeze_experiment, read_json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, responses, out = root / 'input.jsonl', root / 'responses.jsonl', root / 'run'
            pair = {'id': 'a', 'english': 'Alice buys 3 apples.', 'gloss': 'fs-ALICE BUY 9 APPLE', 'source_group': 'doc'}
            source.write_text(json.dumps(pair) + '\n', encoding='utf-8')
            fixtures = []
            for task in ('english', 'gloss'):
                fixtures.append({'task': task, 'input': {'language': task, 'text': pair[task]},
                    'response': {'text': json.dumps({'facts': record(pair[task], task, 'authored')['facts']}),
                                 'finish_reason': 'stop', 'prompt_tokens': 1, 'completion_tokens': 1}})
            checks = {key: {'status': 'UNKNOWN', 'reason': 'authored abstention',
                      'english_evidence': [], 'gloss_evidence': []} for key in record('', 'gloss', '')['facts']}
            fixtures.append({'task': 'judge', 'input': {key: pair[key] for key in ('english', 'gloss')},
                             'response': {'text': json.dumps({'checks': checks}), 'finish_reason': 'stop',
                                          'prompt_tokens': 1, 'completion_tokens': 1}})
            responses.write_text(''.join(json.dumps(x) + '\n' for x in fixtures), encoding='utf-8')
            frozen = freeze_experiment(source, default_config(), 'a' * 40, 'replay')
            run_experiment(source, frozen, out, ReplayBackend(responses))
            rows = [json.loads(line) for line in (out / 'records.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(rows[0]['arms']['cpu']['checks']['numbers']['status'], 'MISMATCH')
            self.assertEqual(rows[0]['arms']['structured']['checks']['numbers']['status'], 'UNKNOWN')
            self.assertEqual(rows[0]['arms']['judge']['checks']['numbers']['status'], 'UNKNOWN')
            backend = ReplayBackend(responses)
            backend.generate = lambda requests: self.fail('Cached requests must not execute again')
            run_experiment(source, frozen, out, backend)
            manifest = read_json(out / 'manifest.json')
            self.assertEqual(manifest['backend']['kind'], 'replay')
            self.assertFalse(manifest['cuda_inference'])
            self.assertEqual(manifest['status'], 'complete')
            self.assertEqual(len(list((out / 'cache').glob('*.json'))), 3)

    def test_truncation_and_invalid_json_are_failures_not_model_predictions(self):
        from signir.gpu.runner import interpret_response
        pair = {'english': 'buy', 'gloss': 'BUY'}
        for response in ({'text': '{}', 'finish_reason': 'length'},
                         {'text': 'not json', 'finish_reason': 'stop'},
                         {'error': 'CUDA out of memory', 'text': '', 'finish_reason': 'error'}):
            with self.subTest(response=response):
                result = interpret_response('english', pair, response)
                self.assertEqual(result['status'], 'error')
                self.assertIsNone(result['record'])
                self.assertTrue(result['error'])

    def test_modified_cache_is_rejected(self):
        from signir.gpu.runner import cached_generate
        from signir.gpu.storage import read_json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            backend = SimpleNamespace(identity={'kind': 'replay'},
                generate=lambda requests: [{'text': '{}', 'finish_reason': 'stop'} for request in requests])
            requests = [{'task': 'judge', 'messages': [], 'schema': {}}]
            cached_generate(requests, {'freeze_id': 'a'}, path, backend, 1)
            target = next(path.glob('*.json'))
            changed = read_json(target)
            changed['response']['text'] = '{"changed":true}'
            target.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaises(ValueError):
                cached_generate(requests, {'freeze_id': 'a'}, path, backend, 1)

    def test_output_cannot_contain_input_or_alias_it(self):
        from signir.gpu.storage import protect_output
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.jsonl'
            source.write_text('original', encoding='utf-8')
            alias = root / 'alias'
            alias.symlink_to(source)
            for output in (root, source, alias):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    protect_output(output, [source])
            self.assertEqual(source.read_text(encoding='utf-8'), 'original')

    def test_real_backend_refuses_replay_freeze_before_model_load(self):
        from signir.gpu.backend import CUDABackend
        with self.assertRaisesRegex(ValueError, 'replay'):
            CUDABackend({'container_image': 'replay'})


if __name__ == '__main__':
    unittest.main()
