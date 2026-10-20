"""Isolated report bundles with row-level failures and reproducible request artifacts."""
import csv
import importlib.metadata
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from signir.data import file_hash

from .data import ensure_distinct_paths, validate_rows

from .audit import audit, _source
from .client import ExtractionError, sha256
from .compare import compare_graphs
from .extract import PROMPT, extract_graph, extraction_schema
from .schema import Graph


OUTPUTS = ("records.jsonl", "traces.jsonl", "checks.csv", "summary.json", "manifest.json")


def preflight(out, inputs=()):
    out = Path(out)
    ensure_distinct_paths(inputs, [out / name for name in OUTPUTS])
    if out.exists() or out.is_symlink():
        raise ValueError("event output directory must be new; choose a separate run directory")


def _manifest(inputs, client=None, lexicon=None):
    package = Path(__file__).resolve().parents[1]
    return {
        "engine": "event-v1-experimental", "schema_version": "2.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_hashes": {str(p): file_hash(p) for p in inputs},
        "code_hashes": {str(p.relative_to(package)): file_hash(p) for p in sorted(package.rglob("*.py"))},
        "schema_sha256": sha256(Graph.model_json_schema()),
        "extraction_schema_sha256": sha256(extraction_schema()), "prompt_sha256": sha256(PROMPT),
        "lexicon_sha256": lexicon.fingerprint() if lexicon else None,
        "config": client.config.model_dump() if client else None,
        "config_sha256": sha256(client.config.model_dump()) if client else None,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    **{name: importlib.metadata.version(name) for name in ("pydantic", "scipy", "numpy")}},
        "model_execution": "configured_endpoint" if client else "saved_graphs_only",
        "model_revision_verification": "Model name is checked; revision is operator-declared, not attested.",
        "interpretation": "Schema and software validation do not establish extraction or ASL accuracy.",
    }


def _write_bundle(out, records, traces, manifest):
    out = Path(out)
    preflight(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = audit(records)
    with tempfile.TemporaryDirectory(prefix=".signir-events-", dir=out.parent) as temp:
        stage = Path(temp) / "report"
        stage.mkdir(mode=0o700)

        def write(name, text):
            path = stage / name
            with open(path, "x", encoding="utf-8", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
                f.write(text)

        for name, rows in [("records.jsonl", records), ("traces.jsonl", traces)]:
            write(name, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))
        write("summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        with open(stage / "checks.csv", "x", encoding="utf-8", newline="",
                                       opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            names = ["id", "state", "english_event", "gloss_event", "field", "item", "status", "reason"]
            writer = csv.DictWriter(f, fieldnames=names)
            writer.writeheader()
            for row in records:
                if row["state"] == "error":
                    writer.writerow({"id": row["id"], "state": "error", "reason": row["error"]["code"]})
                for check in row["checks"]:
                    writer.writerow({"id": row["id"], "state": row["state"],
                                     **{k: check[k] for k in names[2:]}})
        manifest["output_hashes"] = {name: file_hash(stage / name) for name in OUTPUTS if name != "manifest.json"}
        manifest["n_pairs"] = len(records)
        manifest["error_pairs"] = summary["error_pairs"]
        write("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        if out.exists():
            raise ValueError("output directory appeared during run; refusing overwrite")
        stage.rename(out)
    return summary


def run_batch(rows, out, client, lexicon=None, inputs=()):
    rows = validate_rows(rows)
    preflight(out, inputs)
    manifest = _manifest(inputs, client, lexicon)
    records, traces = [], []
    for row in rows:
        source = {s: row[s] for s in ("english", "gloss")}
        record = {"id": row["id"], "source": source, "source_group": row["source_group"],
                  "provenance": row["provenance"], "state": "ok", "checks": []}
        # Per-side calls are independent even when one fails, retaining diagnostics.
        failures, graphs = [], {}
        for side in ("english", "gloss"):
            first = len(client.traces)
            try:
                if not source[side].strip():
                    raise ExtractionError("empty_source", f"{side} source is empty")
                graphs[side] = extract_graph(source[side], side, client, lexicon)
                record[side] = graphs[side].model_dump()
            except ExtractionError as exc:
                failures.append({"side": side, "code": exc.code, "message": str(exc)})
            traces.extend({"pair_id": row["id"], "side": side, **trace}
                          for trace in client.traces[first:])
        if failures:
            record.update(state="error", error={"code": "extraction_failed", "failures": failures})
        else:
            record.update(compare_graphs(graphs["english"], graphs["gloss"]))
        records.append(record)
    return _write_bundle(out, records, traces, manifest)


def run_saved(rows, out, inputs=()):
    preflight(out, inputs)
    ids = [row.get("id") for row in rows]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("saved records require unique nonempty IDs")
    sources = [_source(row) for row in rows]
    manifest = _manifest(inputs)
    records = []
    for row, source in zip(rows, sources):
        record = {"id": row["id"], "source": source, "state": "ok", "checks": [],
                  "provenance": row.get("provenance", {"kind": "saved_graph", "version": "2.0"})}
        try:
            if row.get("state") == "error":
                raise ValueError("saved extraction error cannot be reclassified as linguistic UNKNOWN")
            a, b = Graph.model_validate(row["english"]), Graph.model_validate(row["gloss"])
            if a.text != source["english"] or b.text != source["gloss"]:
                raise ValueError("saved graph text differs from original source")
            record.update(english=a.model_dump(), gloss=b.model_dump(), **compare_graphs(a, b))
        except (ValueError, KeyError, TypeError) as exc:
            record.update(state="error", error={"code": "invalid_saved_graph", "message": str(exc)})
        records.append(record)
    return _write_bundle(out, records, [], manifest)
