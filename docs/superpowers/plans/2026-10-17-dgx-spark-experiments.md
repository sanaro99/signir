# DGX Spark experiments implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user authorized implementation and upload after discussing this experiment.

**Goal:** Deliver a reproducible CUDA inference experiment and CPU replay smoke test.

**Architecture:** An optional signir.gpu package owns strict output contracts,
frozen inputs, CUDA/vLLM inference, caching, annotation export and evaluation.
Existing CPU readers remain the baseline. All arms use the same comparison guards.

**Tech Stack:** Python 3.11+, standard library, existing natural extra, PyTorch/vLLM from the DGX Spark container.

**Spec:** docs/superpowers/specs/2026-10-17-dgx-spark-experiments.md

## Global constraints

- Actual inference requires CUDA; replay never claims GPU execution.
- English and gloss extraction requests are independent and exclude all labels.
- Model/tokenizer commit, image digest, source, prompts, input and settings are frozen.
- No private data or unrelated existing changes are uploaded.
- Keep unsupported roles, polarity and event alignment UNKNOWN.

## Review focus

- Changed input, prompts, dependencies or code cannot reuse an old freeze/cache.
- Invalid model JSON, evidence, nested types and truncation remain visible failures.
- Missing annotations and UNKNOWN outcomes cannot inflate detection accuracy.
- Output paths cannot overwrite inputs, gold files, configs or freezes.
- CUDA failure stops actual inference; replay artifacts are clearly identified.

### Task 1: Independent contracts and frozen data

**Files:** signir/gpu/protocol.py, signir/gpu/storage.py, experiments/dgx-spark/prompts/, tests/test_gpu_protocol.py

**Interfaces:** request(task, pair) returns messages/schema; parse_extraction(payload, text, language) returns validated SignIR; freeze(input, config, revision, image) returns immutable fingerprints.

- [x] Write tests for source-side isolation, evidence/type rejection, gloss abstention, duplicate IDs and split leakage, changed-input freeze refusal.
- [x] Run tests and observe failure because the new package is absent.
- [x] Implement contracts, versioned prompts, strict data loading and freeze verification.
- [x] Run the focused tests and commit the completed unit.

### Task 2: CUDA inference and resumable three-arm runner

**Files:** signir/gpu/backend.py, signir/gpu/runner.py, signir/gpu/__main__.py, tests/test_gpu_runner.py

**Interfaces:** backend.generate(requests) returns raw outputs with finish reasons and usage; run(input, freeze, out, backend) writes records, cache and manifests.

- [x] Write tests for CUDA rejection, failed/truncated output retention, exact replay/resume, cache invalidation and output alias rejection.
- [x] Run failing tests, implement backend/runner/CLI, and rerun focused tests.
- [x] Preserve baseline setup failures as errors; never relabel them as semantic UNKNOWN.
- [x] Commit the completed runner.

### Task 3: Evaluation, annotation and DGX handoff

**Files:** signir/gpu/evaluation.py, experiments/dgx-spark/{README.md,config.json,run.sh,fixtures/}, tests/test_gpu_evaluation.py, README.md

**Interfaces:** evaluate(records, gold) returns coverage and optional correctness metrics; export_annotations(input, out) writes independent blank sheets; CLI exposes freeze/run/replay/annotate/score/preflight.

- [x] Test missing-label denominators, abstentions as missed errors, unsupported assertions, gold comparator control, and blind sheets.
- [x] Implement reports, authored fixtures, launch script and runbook.
- [x] Execute the replay smoke workflow and complete existing/new test suite; syntax-check launcher and build/install wheel.
- [x] Review the complete branch and address material findings with regression tests.
- [x] Publish the verified feature branch and attach its pull request: https://github.com/sanaro99/signir/pull/1.
