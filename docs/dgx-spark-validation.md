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
