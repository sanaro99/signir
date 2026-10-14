# Implementation plan

Execute inline, in dependency order, with standard-library unittest tests.

- `signir/schema.py`, `english.py`, `gloss.py`, `compare.py`: versioned records,
  independent extraction and deterministic comparisons. Core tests first.
- `signir/data.py`: strict JSONL, stable IDs, prior-run adapter, connected groups,
  reproducible splits, hashes. Test duplicate chains and ambiguous joins.
- `signir/controlled.py`, bundled `fixtures/`: authored fixture families and
  controlled edits, with independent expected checks and gold values.
- `signir/baselines.py`: reproduce earlier lexical-core Sign F1 exactly, add raw
  token multiset F1. Confirm parity by executing the old implementation locally.
- `signir/evaluate.py`: development-only calibration, freeze and verification,
  per-check and per-error CSV, JSON evidence, coverage, audited error sources.
- `signir/correction.py`: one-call adapter contract and saved responses; test
  missing responses, regression retention and no repeated repair.
- `signir/cli.py`, `__main__.py`, packaging, docs: install and exercise all commands.
- `scripts/inventory.py`: metadata-only inventory of accessible earlier files;
  run selected natural-output feasibility into ignored storage.

Acceptance requires the full test suite, a clean environment install, demo,
file checking, fixture generation, preparation, freeze/evaluation, correction,
and fixed-run import/coverage. No claim of natural extraction accuracy without
reviewed gold annotations. No private corpus text is copied into public fixtures.
