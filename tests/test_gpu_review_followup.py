import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


class GPUReviewFollowupTests(unittest.TestCase):
    def test_suite_publishes_complete_scoring_and_rejects_changed_reports(self):
        from signir.gpu.challenge import build_challenge
        from signir.gpu.runner import unknown_checks
        from signir.gpu.suite import run_suite
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            def fake_launch(*args, **kwargs):
                target = output/'inference/run/records.jsonl'
                target.parent.mkdir(parents=True, exist_ok=True)
                rows = [{**pair, 'arms': {name: {'status':'ok', 'checks':unknown_checks('mock')}
                        for name in ('cpu','structured','judge')}} for pair in build_challenge()[0]]
                target.write_text(''.join(json.dumps(item)+'\n' for item in rows))
                return SimpleNamespace(returncode=0)
            with patch('signir.gpu.suite.subprocess.run', side_effect=fake_launch) as launch:
                self.assertEqual(run_suite(output), 0)
                self.assertTrue((output/'scored/complete.json').is_file())
                self.assertTrue((output/'scored/report.md').is_file())
                self.assertEqual(run_suite(output), 0)
                (output/'scored/report.md').write_text('interrupted or edited')
                with self.assertRaisesRegex(ValueError, 'Changed'):
                    run_suite(output)
                self.assertEqual(launch.call_count, 2)

    def test_cuda_setup_failure_keeps_truthful_attempt_telemetry(self):
        from signir.gpu.runner import run_experiment
        backend = SimpleNamespace(identity={'kind':'cuda-vllm'}, metrics={'batches':[]})
        frozen = {'freeze_id':'test'}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'run'
            with patch('signir.gpu.runner.verify_freeze', return_value=[]), \
                    patch('signir.gpu.runner.execute', side_effect=RuntimeError('model initialization failed')):
                with self.assertRaisesRegex(RuntimeError, 'model initialization failed'):
                    run_experiment(Path(directory)/'input', frozen, output, backend)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertFalse(manifest['cuda_inference'])
            self.assertEqual(manifest['backend_metrics'], {'batches':[]})
            self.assertGreaterEqual(manifest['attempt_wall_seconds'], 0)

    def test_partial_challenge_stops_before_gpu_launch(self):
        from signir.gpu.suite import run_suite
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output/'challenge').mkdir()
            (output/'challenge/pairs.jsonl').write_text('{}\n')
            with patch('signir.gpu.suite.subprocess.run') as launch:
                with self.assertRaisesRegex(ValueError, 'Incomplete|Changed'):
                    run_suite(output)
                launch.assert_not_called()

    def test_partial_scoring_stops_before_gpu_launch(self):
        from signir.gpu.challenge import write_challenge
        from signir.gpu.suite import run_suite
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_challenge(output/'challenge')
            (output/'scored').mkdir()
            with patch('signir.gpu.suite.subprocess.run') as launch:
                with self.assertRaisesRegex(ValueError, 'Incomplete'):
                    run_suite(output)
                launch.assert_not_called()

    def test_one_invalid_request_does_not_poison_valid_batch_neighbors(self):
        from signir.gpu.runner import cached_generate
        def generate(requests):
            if any(row['task'] == 'oversized' for row in requests):
                raise ValueError('prompt exceeds context length')
            return [{'text': '{}', 'finish_reason': 'stop'} for row in requests]
        backend = SimpleNamespace(identity={'kind': 'replay'}, generate=generate)
        requests = [{'task': task} for task in ('english', 'oversized', 'gloss', 'judge')]
        with tempfile.TemporaryDirectory() as directory:
            results = cached_generate(requests, {'freeze_id': 'a'}, directory, backend, 4)
            self.assertEqual([item['finish_reason'] for item in results], ['stop', 'error', 'stop', 'stop'])

    def test_report_failure_does_not_leave_complete_manifest(self):
        from signir.gpu.__main__ import main
        root = Path(__file__).resolve().parents[1]
        fixtures = root / 'experiments/dgx-spark/fixtures'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.assertEqual(main(['freeze', '--input', str(fixtures/'pairs.jsonl'), '--revision', 'a'*40,
                '--container-image', 'replay', '--out', str(out/'freeze.json')]), 0)
            with patch('signir.gpu.evaluation.write_reports', side_effect=OSError('output disk full')):
                status = main(['replay', '--input', str(fixtures/'pairs.jsonl'), '--freeze', str(out/'freeze.json'),
                    '--responses', str(fixtures/'responses.jsonl'), '--out', str(out/'run')])
            self.assertEqual(status, 2)
            manifest = json.loads((out/'run/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertIn('disk full', manifest['error'])

    def test_token_budget_guard_preserves_neighbor_requests(self):
        from signir.gpu.backend import partition_token_budgets
        class Tokenizer:
            def apply_chat_template(self, messages, **kwargs):
                return [0] * len(messages[0]['content'])
        requests = [{'task': 'english', 'messages': [{'role': 'user', 'content': text}]} for text in ('short', 'x'*90)]
        valid, rejected, lengths = partition_token_budgets(requests, Tokenizer(), 100, 20)
        self.assertEqual(valid, [0])
        self.assertIn('context', rejected[1]['error'].lower())
        self.assertEqual(lengths, [5, 90])


if __name__ == '__main__':
    unittest.main()
