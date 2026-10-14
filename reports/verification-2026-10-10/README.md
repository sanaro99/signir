# Fresh verification: SignIR-Check

Date: 2026-10-10 (America/Los_Angeles). Package 0.1.0.

The existing product code was tested without modifications. This report is a new run, not a summary of cached results.

## Outcomes

- Existing suite: 25 passed, zero failures/errors (14 core, 9 workflow, 2 CLI).
- Controlled evaluation: 20/20 primary errors detected; 160/160 expected statuses; 20 UNKNOWN results; 87.5% check coverage.
- Authored fixture gold: 320/320 side/check values agreed. This is not independent natural-ASL validation.
- Natural audit: all five checks UNKNOWN for all 643 pairs; no independent gold available.
- Baseline parity: 647 comparisons, zero differences from the recovered earlier Sign F1 functions.
- Four deliberate invalid runs were rejected as expected (exit 2).
- Both correction examples used one saved response; the intended entity regression was recorded.
- Installed package smoke passed; its 12 module hashes equal source. Original corpus inputs and source were unchanged.

## How the existing tests work

Core tests exercise actual extraction and comparison functions against literal expected statuses, values and evidence offsets. They include missing markers, wrong-action negation, attached counts, role reversal, unsupported inputs and repetition.

Workflow tests cover connected duplicate/document/variant groups, invalid splits/IDs, exact corpus joins and ambiguous joins, baseline edge cases, reporting denominators, dev-only calibration, frozen input rejection, and exactly one correction call.

CLI tests launch real command-line processes and check produced records for the complete workflow. They do not validate all possible inputs. No stress test, exhaustive proof, GPU test or human ASL judgment was performed.

## Fresh rerun method

Synthetic examples were regenerated and prepared. Their SHA-256 exactly matched the original frozen data. The original freeze was reused, including its original development-selected thresholds; only its 32 test rows were evaluated.

Independent safeguard probes used copies: one extra input newline, a changed stored rule signature, a changed Sign F1 threshold, and identical English split across dev/test. Each was expected to exit 2 and was checked for that result.

Natural outputs were imported again from the single selected prior run, grouped and audited. Corpus text and detailed natural diagnostics remain in private/verification-2026-10-10/. This public folder contains only safe natural aggregates and synthetic data.

## Interpretation

The program is a working research foundation for evaluating improved readers. It is not yet a validated natural-gloss checker. Raw word F1 detected all 20 controlled errors too, so no detection advantage over that baseline is claimed. UNKNOWN is a legitimate abstention, not a verified match or error.

## Commands and logs

Run from D:/gitgit/signir. Commands below use the existing .venv interpreter. Logged destinations are this dated verification folder; freeze files are not overwritten. Private data access is needed for the natural audit and old-baseline parity command.

### Existing suite

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Log: [logs/01-tests.txt](logs/01-tests.txt)

### Build synthetic examples

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir build-controlled --out D:/gitgit/signir/reports/verification-2026-10-10/controlled.jsonl
```

Log: [logs/02-build-synthetic-examples.txt](logs/02-build-synthetic-examples.txt)

### Prepare grouped data

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir prepare D:/gitgit/signir/reports/verification-2026-10-10/controlled.jsonl --out D:/gitgit/signir/reports/verification-2026-10-10/prepared.jsonl
```

Log: [logs/03-prepare-grouped-data.txt](logs/03-prepare-grouped-data.txt)

### Replay original freeze

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir evaluate D:/gitgit/signir/reports/verification-2026-10-10/prepared.jsonl --freeze D:/gitgit/signir/reports/controlled-v1/freeze.json --out D:/gitgit/signir/reports/verification-2026-10-10/evaluation
```

Log: [logs/04-replay-original-freeze.txt](logs/04-replay-original-freeze.txt)

### Check demo file

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir check-file signir/fixtures/demo.jsonl --out D:/gitgit/signir/reports/verification-2026-10-10/demo-checks
```

Log: [logs/05-check-demo-file.txt](logs/05-check-demo-file.txt)

### Replay correction examples

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir correct signir/fixtures/correction-inputs.jsonl --responses signir/fixtures/corrections.json --out D:/gitgit/signir/reports/verification-2026-10-10/correction
```

Log: [logs/06-replay-correction-examples.txt](logs/06-replay-correction-examples.txt)

### Installed package smoke

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -I -c "import signir; from signir.compare import check_pair; print(signir.__file__); assert check_pair(\"Alice buys 3 apples.\", \"fs-ALICE BUY 9 APPLE\")[\"checks\"][\"numbers\"][\"status\"] == \"MISMATCH\"; print(\"PASS\")"
```

Log: [logs/07-installed-package-smoke.txt](logs/07-installed-package-smoke.txt)

### Import saved natural outputs

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir import-prior --predictions D:/gitgit/sign_language_gen/results/asllrp_strat_gpt54mini_baseline_20260910T173514Z/predictions.jsonl --manifest D:/gitgit/sign_language_gen/results/asllrp_strat_gpt54mini_baseline_20260910T173514Z/manifest.json --corpus D:/gitgit/sign_language_gen/data/processed/asllrp_strat/test.jsonl --out D:/gitgit/signir/private/verification-2026-10-10/imported.jsonl
```

Log: [logs/08-import-saved-natural-outputs.txt](logs/08-import-saved-natural-outputs.txt)

### Group natural outputs

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir prepare D:/gitgit/signir/private/verification-2026-10-10/imported.jsonl --out D:/gitgit/signir/private/verification-2026-10-10/prepared.jsonl
```

Log: [logs/09-group-natural-outputs.txt](logs/09-group-natural-outputs.txt)

### Natural feasibility audit

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe -m signir feasibility D:/gitgit/signir/private/verification-2026-10-10/prepared.jsonl --out D:/gitgit/signir/private/verification-2026-10-10/feasibility
```

Log: [logs/10-natural-feasibility-audit.txt](logs/10-natural-feasibility-audit.txt)

### Recover Sign F1 parity

Expected exit: 0. Observed exit: 0.

```text
.venv/Scripts/python.exe scripts/verify_prior_baseline.py --source D:/gitgit/sign_language_gen/src/aslgloss/evaluation/sign_selection.py --predictions D:/gitgit/sign_language_gen/results/asllrp_strat_gpt54mini_baseline_20260910T173514Z/predictions.jsonl --out D:/gitgit/signir/reports/verification-2026-10-10/baseline-parity.json
```

Log: [logs/11-recover-sign-f1-parity.txt](logs/11-recover-sign-f1-parity.txt)

### Reject changed input bytes

Expected exit: 2. Observed exit: 2.

```text
.venv/Scripts/python.exe -m signir evaluate D:/gitgit/signir/reports/verification-2026-10-10/guards/changed-data.jsonl --freeze D:/gitgit/signir/reports/controlled-v1/freeze.json --out D:/gitgit/signir/reports/verification-2026-10-10/guards/rejected-data
```

Log: [logs/12-reject-changed-input-bytes.txt](logs/12-reject-changed-input-bytes.txt)

### Reject changed rule signature

Expected exit: 2. Observed exit: 2.

```text
.venv/Scripts/python.exe -m signir evaluate D:/gitgit/signir/reports/verification-2026-10-10/prepared.jsonl --freeze D:/gitgit/signir/reports/verification-2026-10-10/guards/changed-rules.json --out D:/gitgit/signir/reports/verification-2026-10-10/guards/rejected-rules
```

Log: [logs/13-reject-changed-rule-signature.txt](logs/13-reject-changed-rule-signature.txt)

### Reject changed threshold

Expected exit: 2. Observed exit: 2.

```text
.venv/Scripts/python.exe -m signir evaluate D:/gitgit/signir/reports/verification-2026-10-10/prepared.jsonl --freeze D:/gitgit/signir/reports/verification-2026-10-10/guards/changed-threshold.json --out D:/gitgit/signir/reports/verification-2026-10-10/guards/rejected-threshold
```

Log: [logs/14-reject-changed-threshold.txt](logs/14-reject-changed-threshold.txt)

### Reject split leakage

Expected exit: 2. Observed exit: 2.

```text
.venv/Scripts/python.exe -m signir prepare D:/gitgit/signir/reports/verification-2026-10-10/guards/leakage.jsonl --out D:/gitgit/signir/reports/verification-2026-10-10/guards/rejected-leakage.jsonl
```

Log: [logs/15-reject-split-leakage.txt](logs/15-reject-split-leakage.txt)

## Evidence files

- `verification.json`: summary, environment, commands and integrity hashes.
- `evaluation/report.json` and CSVs: controlled results, separate cohorts and denominators.
- `evaluation/records.jsonl`: both fact records and supporting evidence for synthetic test cases.
- `natural-summary.json`: aggregate-only natural audit.
- `baseline-parity.json`: exact prior-metric compatibility results.
- `correction/records.jsonl`: before/after outputs and checker transitions.
- `guards/`: deliberately invalid synthetic test copies; do not treat as evaluation inputs.

PDF: ../../output/pdf/signir-check-test-report-2026-10-10.pdf
