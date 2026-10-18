# DGX Spark experiment validation, October 17, 2026

The optional experiment was implemented in an isolated worktree based on
`081c8c7696a6db8f8bf934a398f738b9929273cc`. Existing uncommitted research changes
in the original checkout were preserved and are not part of this branch.

## Executed locally

- Full existing and new suite: **71 tests passed**, using a separate Linux Python
  3.11 environment with the documented natural extra and English model.
- The documented authored replay workflow completed: freeze, all three arms,
  scoring against authored expectations, and blind annotation export.
- Warm-cache resume passed. Replay manifests explicitly say `cuda_inference:
  false`; the fixture responses are authored, not outputs of a real model.
- Shell syntax checks passed for all three launch scripts; Python compilation
  and `git diff --check` passed.
- Wheel build/install and packaged-prompt loading passed outside the source tree.
- The actual-inference preflight correctly rejected this CPU environment, which
  has no CUDA-enabled PyTorch installation.

## Independent code review

A read-only reviewer checked the complete implementation at `1c3a828`. Five
material findings were reproduced and fixed with regression tests:

1. Protect the report temporary path against input/freeze aliases.
2. Verify CPU dependency/resource fingerprints during replay.
3. Fingerprint installed transitive distributions for real inference.
4. Fail model initialization before caching any prediction failures.
5. Publish cache entries atomically so interrupted writes cannot poison resume.

Additional regressions verify explicit failed-run manifests and bind check-only
gold to the exact pair text. Scoring preserves failed/UNKNOWN predictions in
known-label denominators and reports no accuracy without reviewed labels.

## Still requires DGX Spark execution

No real CUDA inference, Qwen extraction accuracy, GPU throughput or natural ASL
error-detection result was measured in this environment. The launcher uses the
documented ARM64 Qwen3.8 NVFP4 container recipe, but its actual model load,
structured decoding, CUDA kernels and memory settings need the first Spark smoke
run. Independent linguistic review remains necessary for natural-data claims.

Start with the four public authored pairs in
`experiments/dgx-spark/fixtures/pairs.jsonl`, then use an authorized reviewed pilot.
See the [runbook](../experiments/dgx-spark/README.md) for exact commands.

## Independent review follow-up, October 18, 2026

Three reviewers independently examined CUDA integration, dry-run behavior and
scientific value. They reproduced oversized-input batch poisoning and premature
complete status on report failure. Follow-up review of the extensions caught
absent-oracle scoring, partial suite publication/resume and misleading failed
CUDA setup telemetry. All findings have regression coverage; the final bounded
reviews found no remaining material issue in those fixes.

- Full suite: **85 tests passed**. The reviewed recovery tests also passed in an
  independent process. Authored freeze/replay/scoring/annotation completed again.
- The expanded CPU dry run processed **52 distinct authored pairs across 16
  phenomena**, generating **148 unique requests** from 156 potential requests
  (8 duplicate side calls saved). The frozen CPU baseline assessed **103/208**
  supported checks. This is diagnostic coverage, not natural-ASL accuracy.
- Tokenizer-only profiling used the immutable model revision
  `482ca0f3832238542f8f5295dde86b5f22711d80`, its Rust tokenizer JSON and original
  Jinja chat template with thinking disabled. English prompts were 2,193–2,201
  tokens; gloss 2,192–2,206; direct judge 1,598–1,619. All 148 requests fit the
  8,192-token context with the full 3,072-token output reserve. No weights were
  downloaded. See [aggregate token audit](dgx-spark-token-budget.json).
- The full Transformers tokenizer loader exceeded this host's **512 MiB cgroup
  memory cap**. The lightweight audit succeeded; it is a context-budget check,
  not a vLLM integration or performance test. The documented full-loader audit
  remains available in the Spark container.
- Scored results now include split/phenomenon/annotation strata, a candidate
  review queue, alarm accountability and CPU/model hybrid controls without extra
  inference. Oracle controls are unmeasured without relevant gold side records.
- Serial/default/batch-plus-prefix-cache profiles and fresh-run comparisons are
  available for actual Spark calibration. No speedup has been measured here.

No CUDA inference or natural-data model result has been measured on this host.
The recommended next runs and their deliverables are in the
[independent review/run plan](../experiments/dgx-spark/REVIEW.md).
