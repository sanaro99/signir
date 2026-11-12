"""Minimal Ollama caller for the architecture experiment (no retries, no repair)."""
import json
import time
import urllib.request

URL = 'http://localhost:11434'


def chat(model, messages, schema, num_ctx=8192, max_tokens=1200):
    body = {'model': model, 'messages': messages, 'stream': False, 'think': False, 'format': schema,
            'keep_alive': '30m',
            'options': {'temperature': 0, 'seed': 42, 'num_ctx': num_ctx, 'num_predict': max_tokens}}
    t = time.time()
    req = urllib.request.Request(URL + '/api/chat', json.dumps(body).encode(), {'Content-Type': 'application/json'})
    d = json.load(urllib.request.urlopen(req, timeout=1800))
    return {'text': d['message']['content'], 'seconds': round(time.time() - t, 2),
            'prompt_tokens': d.get('prompt_eval_count'), 'output_tokens': d.get('eval_count'),
            'prompt_seconds': round(d.get('prompt_eval_duration', 0) / 1e9, 2),
            'output_seconds': round(d.get('eval_duration', 0) / 1e9, 2),
            'truncated': d.get('done_reason') == 'length'}


def embed(texts, model='all-minilm'):
    req = urllib.request.Request(URL + '/api/embed', json.dumps({'model': model, 'input': texts}).encode(),
                                 {'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=600))['embeddings']
