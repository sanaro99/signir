import copy
import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_event_schema import graph
from signir.events.client import LocalClient, ModelConfig, ExtractionError
from signir.events.extract import extract_graph
from signir.events.lexicon import Lexicon


def payload():
    data = graph()
    positions = {(0, 5): (0, 1), (6, 9): (1, 2), (10, 11): (2, 3), (12, 16): (3, 4)}

    def tokens(value):
        if isinstance(value, list):
            return [tokens(v) for v in value]
        if isinstance(value, dict):
            if "start" in value:
                a, b = positions[value["start"], value["end"]]
                return {"start_token": a, "end_token": b}
            return {k: tokens(v) for k, v in value.items()}
        return value
    return tokens({k: data[k] for k in ["mentions", "events", "unresolved"]})


@contextmanager
def server(backend="ollama", mutate=None, status=200, broken_chunked=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, request))
            if broken_chunked and len(requests) == 1:
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b'20\r\n{"model": "test"}')
                self.close_connection = True
                return
            response = ({"model": "test", "done": True, "done_reason": "stop",
                         "message": {"content": json.dumps(payload())}}
                        if backend == "ollama" else
                        {"model": "test", "choices": [{"finish_reason": "stop",
                         "message": {"content": json.dumps(payload())}}]})
            if mutate:
                mutate(response)
            body = json.dumps(response).encode()
            self.send_response(status)
            if status == 302:
                self.send_header("Location", "/redirected")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        config = ModelConfig(backend=backend, endpoint=f"http://127.0.0.1:{httpd.server_port}",
                             model="test")
        yield LocalClient(config), requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class ExtractionTests(unittest.TestCase):
    def test_both_protocols_and_source_independence(self):
        for backend in ["ollama", "vllm"]:
            with self.subTest(backend=backend), server(backend) as (client, requests):
                a = extract_graph("ALICE BUY 3 BOOK", "english", client)
                b = extract_graph("ALICE BUY 3 BOOK SECRET", "gloss", client)
                self.assertEqual(a.events[0].quantities[0].value, "3")
                self.assertEqual(b.mentions[1].evidence[0].text, "BOOK")
                self.assertNotIn("SECRET", json.dumps(requests[0][1]))
                self.assertIn("SECRET", requests[1][1]["messages"][1]["content"])
                self.assertEqual(len(requests), 2)
                body = requests[0][1]
                self.assertFalse(body["stream"])
                self.assertIn("format" if backend == "ollama" else "structured_outputs", body)
                self.assertEqual(len(client.traces), 2)
                self.assertTrue(client.traces[0]["response_sha256"])

    def test_truncation_identity_refusal_and_invalid_graph_fail_visibly(self):
        def invalid_span(response):
            p = payload()
            p["events"][0]["evidence"] = [{"start_token": 99, "end_token": 100}]
            response["message"]["content"] = json.dumps(p)

        for mutate, code in [
            (lambda r: r.update(done_reason="length"), "incomplete_response"),
            (lambda r: r.update(model="different"), "model_mismatch"),
            (lambda r: r["message"].update(refusal="no"), "model_refusal"),
            (lambda r: r["message"].update(content="not json"), "invalid_json"),
            (invalid_span, "invalid_graph"),
        ]:
            with self.subTest(code=code), server(mutate=mutate) as (client, _):
                with self.assertRaises(ExtractionError) as error:
                    extract_graph("ALICE BUY 3 BOOK", "english", client)
                self.assertEqual(error.exception.code, code)
                self.assertEqual(client.traces[-1]["error"], code)

    def test_redirect_is_not_followed(self):
        with server(status=302) as (client, requests):
            with self.assertRaises(ExtractionError) as error:
                extract_graph("ALICE BUY 3 BOOK", "english", client)
            self.assertEqual(error.exception.code, "http_error")
            self.assertEqual(len(requests), 1)

    def test_context_and_response_limits(self):
        with server() as (client, requests):
            client.config = client.config.model_copy(update={"max_response_bytes": 10})
            with self.assertRaises(ExtractionError) as error:
                extract_graph("ALICE BUY 3 BOOK", "english", client)
            self.assertEqual(error.exception.code, "response_too_large")
        with server() as (client, requests):
            with self.assertRaises(ExtractionError) as error:
                extract_graph("A" * 100000, "english", client)
            self.assertEqual(error.exception.code, "context_budget_exceeded")
            self.assertEqual(requests, [])

    def test_token_spans_preserve_whitespace(self):
        with server() as (client, _):
            result = extract_graph("ALICE  BUY\n3 BOOK", "english", client)
            self.assertEqual(result.events[0].evidence[0].start, 7)
            self.assertEqual(result.mentions[1].evidence[0].start, 13)

    def test_reader_cannot_silently_drop_reviewed_lexical_alternatives(self):
        lexicon = Lexicon.model_validate({"version": "test", "entries": [
            {"label": "BUY", "concepts": ["buy", "purchase"], "kind": "predicate",
             "provenance": "authored ambiguous fixture"}
        ]})
        with server() as (client, _):
            with self.assertRaises(ExtractionError) as error:
                extract_graph("ALICE BUY 3 BOOK", "gloss", client, lexicon)
            self.assertEqual(error.exception.code, "invalid_graph")
        def retain(response):
            p = payload()
            p["events"][0]["alternatives"] = ["purchase"]
            response["message"]["content"] = json.dumps(p)
        with server(mutate=retain) as (client, _):
            result = extract_graph("ALICE BUY 3 BOOK", "gloss", client, lexicon)
            self.assertEqual(result.events[0].alternatives, ["purchase"])

    def test_vllm_errors_and_duplicate_json_keys(self):
        cases = [
            (lambda r: r["choices"][0].update(finish_reason="length"), "incomplete_response"),
            (lambda r: r["choices"][0]["message"].update(refusal="no"), "model_refusal"),
            (lambda r: r["choices"][0]["message"].update(
                content='{"mentions":[],"mentions":[],"events":[],"unresolved":[]}'), "invalid_json"),
        ]
        for mutate, code in cases:
            with self.subTest(code=code), server("vllm", mutate) as (client, _):
                with self.assertRaises(ExtractionError) as error:
                    extract_graph("ALICE BUY 3 BOOK", "english", client)
                self.assertEqual(error.exception.code, code)

    def test_deep_json_becomes_a_recorded_extraction_error(self):
        def nested(response):
            response["message"]["content"] = "[" * 1500 + "0" + "]" * 1500
        with server(mutate=nested) as (client, _):
            with self.assertRaises(ExtractionError) as error:
                extract_graph("ALICE BUY 3 BOOK", "english", client)
            self.assertEqual(error.exception.code, "invalid_json")
            self.assertEqual(client.traces[-1]["error"], "invalid_json")
