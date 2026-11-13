"""Execution-only throughput changes must not alter what the model is asked."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPARK = ROOT / 'experiments/dgx-spark'


class GPUThroughputTests(unittest.TestCase):
    def test_version_1_requests_are_byte_identical(self):
        # Pinned before the throughput work: prompts, schemas and payloads of the frozen protocol.
        from signir.gpu.protocol import make_request
        from signir.gpu.storage import digest, load_pairs
        pairs = load_pairs(SPARK / 'fixtures/pairs.jsonl')
        requests = [make_request(task, pair) for pair in pairs for task in ('english', 'gloss', 'judge')]
        self.assertEqual(digest(requests), 'b6239ea52fa813849b7c661dea4bccb29f2f5ae6ef5e5f7faba812a03ec23393')

    def test_requests_do_not_share_mutable_schema(self):
        from signir.gpu.protocol import make_request
        pair = {'english': 'a', 'gloss': 'A'}
        first, second = make_request('english', pair), make_request('english', pair)
        first['schema']['properties'].clear()
        self.assertTrue(second['schema']['properties'])

    def test_engine_receives_more_requests_than_concurrent_slots(self):
        # vLLM batches a submitted list itself; handing it exactly batch_size requests
        # leaves slots idle while the slowest request of each batch finishes.
        from signir.gpu.runner import cached_generate, submission_size
        self.assertEqual(submission_size({'batch_size': 4}), 32)
        seen = []

        def generate(requests):
            seen.append(len(requests))
            return [{'text': '{}', 'finish_reason': 'stop'} for _ in requests]
        backend = SimpleNamespace(identity={'kind': 'replay'}, generate=generate)
        requests = [{'task': 'english', 'n': n} for n in range(70)]
        with tempfile.TemporaryDirectory() as directory:
            results = cached_generate(requests, {'freeze_id': 'a'}, directory, backend,
                                      submission_size({'batch_size': 4}))
            self.assertEqual(seen, [32, 32, 6])
            self.assertEqual(len(results), 70)
            # Resume granularity: every finished submission is on disk.
            self.assertEqual(len(list(Path(directory).glob('*.json'))), 70)

    def test_per_request_seconds_use_engine_metrics_when_available(self):
        from signir.gpu.backend import request_seconds
        # Field names of vLLM's RequestStateStats (engine-core monotonic timestamps).
        metrics = SimpleNamespace(arrival_time=1.7e9, queued_ts=10.0, scheduled_ts=12.0,
                                  first_token_ts=12.5, last_token_ts=15.5)
        self.assertEqual(request_seconds(SimpleNamespace(metrics=metrics)),
                         {'queue_seconds': 2.0, 'generation_seconds': 3.5})
        # Unset timestamps default to 0.0 in vLLM: report nothing rather than a made-up time.
        unset = SimpleNamespace(queued_ts=0.0, scheduled_ts=0.0, last_token_ts=0.0)
        self.assertEqual(request_seconds(SimpleNamespace(metrics=unset)), {})
        self.assertEqual(request_seconds(SimpleNamespace(metrics=None)), {})
        self.assertEqual(request_seconds(SimpleNamespace()), {})

    def test_model_load_keeps_request_stats_and_frozen_engine_settings(self):
        # Offline vLLM turns request stats off unless asked; without them the per-request
        # times above are never reported and the submission change cannot be measured.
        import sys
        from unittest.mock import patch
        from signir.gpu.backend import CUDABackend
        seen = {}
        fake = SimpleNamespace(LLM=lambda **kwargs: seen.update(kwargs) or 'engine', SamplingParams=object)
        params = SimpleNamespace(StructuredOutputsParams=object)
        config = json.loads((SPARK / 'config-throughput.json').read_text(encoding='utf-8'))
        backend = CUDABackend.__new__(CUDABackend)
        backend.frozen = {'config': config, 'model_revision': 'r', 'tokenizer_revision': 'r'}
        with patch.dict(sys.modules, {'vllm': fake, 'vllm.sampling_params': params}):
            backend._load_model()
        self.assertIs(seen['disable_log_stats'], False)
        self.assertEqual((seen['max_num_seqs'], seen['enforce_eager'], seen['enable_prefix_caching'],
                          seen['trust_remote_code'], seen['revision']), (8, False, True, False, 'r'))

    def test_profiles_are_valid_and_throughput_uses_cuda_graphs(self):
        from signir.gpu.protocol import validate_config
        profiles = {name: json.loads((SPARK / name).read_text(encoding='utf-8'))
                    for name in ('config.json', 'config-serial.json', 'config-throughput.json')}
        for config in profiles.values():
            validate_config(config)
        # First measured runs stay conservative; the calibration profile turns the engine's
        # own optimizations on (compiled CUDA graphs, prefix cache for the shared system prompt).
        self.assertTrue(profiles['config.json']['enforce_eager'])
        self.assertFalse(profiles['config-throughput.json']['enforce_eager'])
        self.assertTrue(profiles['config-throughput.json']['enable_prefix_caching'])
        decoding = ('model', 'seed', 'temperature', 'top_p', 'max_tokens', 'max_model_len')
        for config in profiles.values():
            self.assertEqual({k: config[k] for k in decoding}, {k: profiles['config.json'][k] for k in decoding})

    def test_launcher_reuses_downloaded_cpu_packages(self):
        text = (SPARK / 'run.sh').read_text(encoding='utf-8')
        self.assertIn('PIP_CACHE_DIR=/model-cache/pip', text)


if __name__ == '__main__':
    unittest.main()
