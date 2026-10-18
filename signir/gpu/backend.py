"""CUDA-only vLLM execution and an explicitly separate fixture replay backend."""
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import time

from .storage import digest, file_hash


def device_snapshot():
    """Device-wide observations, not parent-process allocator/model peaks."""
    result = {'scope': 'device-wide snapshot; not peak model allocation', 'nvidia_smi': None}
    try:
        result['nvidia_smi'] = subprocess.check_output(['nvidia-smi',
            '--query-gpu=name,memory.used,memory.total,utilization.gpu,power.draw',
            '--format=csv,noheader,nounits'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        result['host_memory_kib'] = {line.split(':')[0]: int(line.split()[1])
            for line in Path('/proc/meminfo').read_text().splitlines()
            if line.startswith(('MemTotal:', 'MemAvailable:'))}
    except (OSError, ValueError):
        pass
    return result


def partition_token_budgets(requests, tokenizer, max_model_len, max_tokens):
    valid, rejected, lengths = [], {}, []
    for index, request in enumerate(requests):
        ids = tokenizer.apply_chat_template(request['messages'], tokenize=True,
            add_generation_prompt=True, enable_thinking=False)
        if isinstance(ids, dict):
            ids = ids['input_ids']
        length = len(ids)
        lengths.append(length)
        if length + max_tokens > max_model_len:
            rejected[index] = {'text': '', 'finish_reason': 'error', 'prompt_tokens': length,
                'completion_tokens': 0, 'error': f'Context budget exceeded: {length} prompt + {max_tokens} output > {max_model_len} context'}
        else:
            valid.append(index)
    return valid, rejected, lengths


def cuda_preflight():
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError('CUDA inference requires PyTorch from the DGX Spark vLLM container') from exc
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; actual inference cannot fall back to CPU')
    tensor = torch.ones((16, 16), device='cuda', dtype=torch.float32)
    value = (tensor @ tensor)[0, 0].item()
    torch.cuda.synchronize()
    if tensor.device.type != 'cuda' or value != 16.0:
        raise RuntimeError('CUDA tensor execution did not pass its numerical check')
    result = {'cuda_available': True, 'tensor_device': str(tensor.device),
              'cuda_version': torch.version.cuda, 'torch_version': torch.__version__,
              'device_name': torch.cuda.get_device_name(0),
              'compute_capability': list(torch.cuda.get_device_capability(0)),
              'device_count': torch.cuda.device_count(), 'machine': platform.machine()}
    del tensor
    torch.cuda.empty_cache()
    return result


class CUDABackend:
    def __init__(self, frozen):
        if frozen['container_image'] == 'replay':
            raise ValueError('A replay freeze cannot be used for CUDA inference')
        if os.environ.get('SIGNIR_CONTAINER_IMAGE') != frozen['container_image']:
            raise ValueError('Container digest does not match freeze; use the DGX launcher')
        if os.environ.get('VLLM_TARGET_DEVICE', 'cuda') != 'cuda':
            raise ValueError('vLLM must target CUDA')
        self.frozen = frozen
        self.identity = {'kind': 'cuda-vllm', 'hardware': cuda_preflight(),
                         'vllm_version': version('vllm'), 'image': frozen['container_image']}
        self.engine = None
        self.metrics = {'model_load_seconds': None, 'batches': [], 'initial_device': device_snapshot()}

    def prepare(self):
        if self.engine is not None:
            return
        try:
            start = time.perf_counter()
            self._load_model()
            self.metrics['model_load_seconds'] = time.perf_counter() - start
            self.metrics['loaded_device'] = device_snapshot()
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError('CUDA model initialization failed: ' + str(exc)) from exc

    def _load_model(self):
        from vllm import LLM, SamplingParams
        from vllm.sampling_params import StructuredOutputsParams
        self.sampling_class, self.structured_class = SamplingParams, StructuredOutputsParams
        config = self.frozen['config']
        self.engine = LLM(model=config['model'], revision=self.frozen['model_revision'],
            tokenizer_revision=self.frozen['tokenizer_revision'], dtype='auto',
            tensor_parallel_size=1, max_model_len=config['max_model_len'],
            gpu_memory_utilization=config['gpu_memory_utilization'],
            max_num_seqs=config['batch_size'], seed=config['seed'],
            enforce_eager=config['enforce_eager'], trust_remote_code=False,
            enable_prefix_caching=config.get('enable_prefix_caching', False))

    def generate(self, requests):
        self.prepare()
        config = self.frozen['config']
        valid, rejected, lengths = partition_token_budgets(requests, self.engine.get_tokenizer(),
            config['max_model_len'], config['max_tokens'])
        if not valid:
            return [rejected[index] for index in range(len(requests))]
        selected = [requests[index] for index in valid]
        params = [self.sampling_class(temperature=config['temperature'], top_p=config['top_p'],
                  max_tokens=config['max_tokens'], seed=config['seed'],
                  structured_outputs=self.structured_class(json=request['schema']))
                  for request in selected]
        before = device_snapshot()
        start = time.monotonic()
        outputs = self.engine.chat([request['messages'] for request in selected],
            sampling_params=params, chat_template_kwargs={'enable_thinking': False}, use_tqdm=False)
        elapsed = time.monotonic() - start
        generated = [{'text': output.outputs[0].text,
                 'finish_reason': output.outputs[0].finish_reason,
                 'prompt_tokens': len(output.prompt_token_ids or []),
                 'completion_tokens': len(output.outputs[0].token_ids),
                 'amortized_seconds': elapsed / len(selected)} for output in outputs]
        self.metrics['batches'].append({'phase': 'first-call' if not self.metrics['batches'] else 'subsequent-call',
            'seconds': elapsed, 'requests': len(selected), 'rejected_context_requests': len(rejected),
            'tasks': [request['task'] for request in selected],
            'prompt_tokens': sum(row['prompt_tokens'] for row in generated),
            'completion_tokens': sum(row['completion_tokens'] for row in generated),
            'device_before': before, 'device_after': device_snapshot()})
        result = dict(rejected)
        result.update(zip(valid, generated))
        return [result[index] for index in range(len(requests))]


def replay_key(task, payload):
    return digest({'task': task, 'input': payload})


class ReplayBackend:
    """Replay authored/raw saved responses; these are never GPU measurements."""
    def __init__(self, path):
        self.identity = {'kind': 'replay', 'fixture_sha256': file_hash(path)}
        self.responses = {}
        for line in Path(path).read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = replay_key(row['task'], row['input'])
            if key in self.responses:
                raise ValueError('Duplicate replay input/task')
            self.responses[key] = row['response']

    def generate(self, requests):
        result = []
        for request in requests:
            key = replay_key(request['task'], json.loads(request['messages'][1]['content']))
            if key not in self.responses:
                result.append({'text': '', 'finish_reason': 'error', 'error': 'No saved replay response'})
            else:
                result.append(self.responses[key])
        return result
