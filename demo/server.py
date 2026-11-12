"""Local demo: pick an authored English/gloss pair and run the real checker on it.

    python demo/server.py            # then open http://127.0.0.1:8765

Every result is computed on request by the same code as ``python -m signir check``
(CPU rule readers, built-in lexicon). Nothing is precomputed, nothing leaves this
machine, and the examples are authored: no corpus text is included.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from signir.baselines import sign_f1  # noqa: E402
from signir.compare import check_pair  # noqa: E402
from signir.gloss import is_annotated  # noqa: E402

MAX_TEXT = 600
MAX_BODY = 20_000
NMM_LABELS = ('negation', 'topic')
NOTATIONS = (None, 'asllrp', 'aslg_pc12')
CHECK_FIELDS = ('status', 'confidence', 'reason', 'scope', 'english_value', 'gloss_value',
                'english_evidence', 'gloss_evidence', 'missing')
LOCK = threading.Lock()  # the spaCy pipeline and reader caches are shared


def examples():
    return json.loads((HERE / 'examples.json').read_text(encoding='utf-8'))


def _text(body, key):
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} must be a nonempty string')
    if len(value) > MAX_TEXT:
        raise ValueError(f'{key} is longer than {MAX_TEXT} characters')
    return value.strip()


def run_check(body):
    """The real comparison for one pair, plus the SignIR 2.0 graph each reader produced."""
    if not isinstance(body, dict):
        raise ValueError('request must be a JSON object')
    english, gloss = _text(body, 'english'), _text(body, 'gloss')
    nmm = body.get('nmm') or None
    if nmm is not None:
        if not isinstance(nmm, dict) or any(k not in NMM_LABELS or type(v) is not bool for k, v in nmm.items()):
            raise ValueError('nmm must map negation/topic to true or false')
    notation = body.get('notation') or None
    if notation not in NOTATIONS:
        raise ValueError('notation must be asllrp or aslg_pc12')
    reference = body.get('reference') or None
    if reference is not None and (not isinstance(reference, str) or len(reference) > MAX_TEXT):
        raise ValueError('reference must be a short string')
    start = time.perf_counter()
    with LOCK:
        result = check_pair(english, gloss, nmm, notation)
        seconds = time.perf_counter() - start
        graphs, graph_error = None, None
        if is_annotated(gloss):
            graph_error = 'This gloss uses authored role/polarity annotations; it is read by the fixture reader.'
        else:
            try:
                from signir.events.from_rules import english_graph, gloss_graph
                graphs = {'english': english_graph(english).model_dump(exclude_defaults=True),
                          'gloss': gloss_graph(gloss, nmm, notation).model_dump(exclude_defaults=True)}
            except (ImportError, ValueError) as exc:
                graph_error = f'{type(exc).__name__}: {exc}'
    notes = []
    for side in ('english', 'gloss'):
        for key, label in (('unrecognized', 'not recognized'), ('ambiguous_labels', 'noun or verb, unresolved'),
                           ('unattached_numbers', 'number with no noun'),
                           ('unrecognized_predicates', 'verb outside the dictionary')):
            for span in result[side].get(key) or []:
                notes.append({'side': side, 'kind': label, **span})
    out = {
        'english': result['english']['text'], 'gloss': result['gloss']['text'],
        'nmm': nmm, 'notation': notation,
        'checks': {name: {k: check.get(k) for k in CHECK_FIELDS} for name, check in result['checks'].items()},
        'reader_notes': notes,
        'readers': {'english': result['english'].get('extractor'), 'gloss': result['gloss'].get('extractor')},
        'graphs': graphs, 'graph_error': graph_error,
        'seconds': round(seconds, 4),
    }
    if reference:
        out['baseline'] = {'reference': reference, 'sign_f1': round(sign_f1(gloss, reference), 3)}
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = 'SignIRDemo/1'

    def log_message(self, *args):
        pass

    def _send(self, status, body, content_type='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._send(200, (HERE / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/api/examples':
            self._send(200, examples())
        else:
            self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/api/check':
            return self._send(404, {'error': 'not found'})
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if not 0 < length <= MAX_BODY:
                raise ValueError('request body is empty or too large')
            self._send(200, run_check(json.loads(self.rfile.read(length).decode('utf-8'))))
        except (ValueError, KeyError, TypeError) as exc:  # includes malformed JSON and reader setup errors
            self._send(400, {'error': str(exc)})


def main(argv=None):
    parser = argparse.ArgumentParser(description='SignIR-Check demo (local only)')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    print('Loading the English reader ...', flush=True)
    run_check({'english': 'Alice buys 3 apples.', 'gloss': 'fs-ALICE BUY 3 APPLE'})  # warm up, fail early
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'SignIR-Check demo: http://127.0.0.1:{args.port}  (Ctrl+C to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
