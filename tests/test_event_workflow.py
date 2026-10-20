import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout

from test_event_schema import graph
from test_event_extract import server
from signir.events.workflow import run_batch, run_saved
from signir.events.audit import audit
from signir.events.data import ensure_distinct_paths
from signir.cli import main


def pair(id="one"):
    return {"id": id, "english": "ALICE BUY 3 BOOK", "gloss": "ALICE BUY 3 BOOK",
            "source_group": id, "provenance": {"kind": "authored", "version": "test"}}


class EventWorkflowTests(unittest.TestCase):
    def test_source_aliases_include_hardlinks_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.jsonl'
            source.write_text('original')
            hardlink, symlink = Path(tmp) / 'hardlink', Path(tmp) / 'symlink'
            hardlink.hardlink_to(source)
            symlink.symlink_to(source)
            for alias in [hardlink, symlink]:
                with self.assertRaises(ValueError):
                    ensure_distinct_paths([source], [alias])
            self.assertEqual(source.read_text(), 'original')

    def test_malformed_batch_is_rejected_before_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp, server() as (client, requests):
            row = pair()
            row['provenance'] = {'kind': 'authored', 'version': False}
            with self.assertRaises(ValueError):
                run_batch([row], Path(tmp) / 'out', client)
            self.assertEqual(requests, [])

    def test_batch_preserves_errors_denominator_and_traces(self):
        with tempfile.TemporaryDirectory() as tmp, server() as (client, requests):
            rows = [pair(), pair("empty")]
            rows[1]["gloss"] = ""
            report = run_batch(rows, Path(tmp) / "out", client)
            self.assertEqual(report["n_pairs"], 2)
            self.assertEqual(report["error_pairs"], 1)
            records = [json.loads(x) for x in (Path(tmp) / "out/records.jsonl").read_text().splitlines()]
            self.assertEqual(records[1]["state"], "error")
            self.assertEqual(records[1]["source"]["gloss"], "")
            self.assertTrue((Path(tmp) / "out/manifest.json").exists())
            self.assertEqual(len(requests), 3)
            self.assertEqual(audit(records)["n_pairs"], 2)

    def test_batch_preflight_does_not_contact_model_or_overwrite_inputs(self):
        with tempfile.TemporaryDirectory() as tmp, server() as (client, requests):
            out = Path(tmp) / "out"
            out.mkdir()
            source = out / "records.jsonl"
            source.write_text("original")
            with self.assertRaises(ValueError):
                run_batch([pair()], out, client, inputs=[source])
            self.assertEqual(source.read_text(), "original")
            with self.assertRaises(ValueError):
                run_batch([pair(), pair()], Path(tmp) / "duplicate", client)
            self.assertEqual(requests, [])

    def test_saved_cli_and_wrong_side_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "saved.jsonl", Path(tmp) / "out"
            record = {"id": "one", "english": graph(), "gloss": graph("gloss")}
            src.write_text(json.dumps(record) + "\n")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["event-compare", str(src), "--out", str(out)]), 0)
            self.assertTrue((out / "summary.json").exists())
            record["gloss"]["language"] = "english"
            result = run_saved([record], Path(tmp) / "wrong")
            self.assertEqual(result["error_pairs"], 1)

    def test_audit_rejects_missing_pairs_changed_text_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_saved([{"id": "one", "english": graph(), "gloss": graph("gloss")}], Path(tmp) / "out")
            row = json.loads((Path(tmp) / "out/records.jsonl").read_text())
            for baseline in [[], [row, row]]:
                with self.assertRaises(ValueError):
                    audit([row], baseline=baseline)
            changed = copy.deepcopy(row)
            changed["source"]["gloss"] = "different"
            with self.assertRaises(ValueError):
                audit([row], baseline=[changed])

    def test_human_unknown_misses_and_errors_remain_in_recall(self):
        records = [
            {"id": "one", "source": {"english": "E", "gloss": "G"}, "state": "error", "checks": []},
            {"id": "two", "source": {"english": "E2", "gloss": "G2"}, "state": "ok",
             "checks": [{"english_event": "e", "gloss_event": "g", "field": "numbers",
                         "item": "q", "status": "MISMATCH", "reason": "test"}]},
        ]
        labels = [{
            "id": r["id"], **r["source"], "reviewer": "independent tester",
            "annotation_source": "independent_human",
            "checks": [{"english_event": "e", "gloss_event": "g", "field": "numbers",
                        "item": "q", "status": "MISMATCH"}],
        } for r in records]
        result = audit(records, labels=labels)
        self.assertEqual(result["human_evaluation"]["mismatch_recall"], 0.5)
        self.assertEqual(result["human_evaluation"]["abstentions_or_errors"], 1)
        labels[0]["annotation_source"] = "model"
        with self.assertRaises(ValueError):
            audit(records, labels=labels)

    def test_broken_http_framing_keeps_failed_and_later_rows(self):
        with tempfile.TemporaryDirectory() as tmp, server(broken_chunked=True) as (client, requests):
            result = run_batch([pair("broken"), pair("later")], Path(tmp) / "out", client)
            self.assertEqual(result["n_pairs"], 2)
            self.assertEqual(result["error_pairs"], 1)
            self.assertEqual(len(requests), 4)
            self.assertEqual(client.traces[0]["error"], "transport_error")
            records = [json.loads(line) for line in (Path(tmp) / "out/records.jsonl").read_text().splitlines()]
            self.assertEqual(records[1]["state"], "ok")
