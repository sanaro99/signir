# Independent review and practical GPU run plan

Three independent reviewers assessed the published head `d329e74` for GPU
integration, scientific usefulness, and behavioral dry runs. Their initial full
suite and replay passed (71 tests), but review found two reproducible failures:

1. An oversized input could poison every cached response in its batch.
2. Report publication could fail after the run was marked complete.

Regression tests reproduce both failures. Exact per-request token budgeting and
validation-error isolation now protect batch neighbors. Report publication is
inside the run lifecycle; failures leave an explicit failed manifest.

A follow-up review also caught a scoring error in the new oracle controls:
checks-only gold was counted as a failed oracle prediction. Those controls now
require the relevant annotated side for eligibility. Absent annotations are
reported separately, with unmeasured quality when no pair qualifies.

The launch follow-up reproduced two additional issues: incomplete challenge or
score directories could be mistaken for finished outputs, and model-load failure
could retain a misleading CUDA flag. The suite now validates complete inputs,
publishes challenge/scored directories only after completion, and fingerprints
every scored artifact. Partial or changed outputs stop before GPU setup. Failed
attempts preserve timing, cache/backend metrics and observed CUDA batch status.

## What GPU time should produce

| Run | Purpose | Concrete artifacts |
|---|---|---|
| Four-pair smoke | Verify actual model load, CUDA kernels and JSON decoding | CUDA/runtime manifest, raw responses, failure report |
| 52-pair authored challenge | Probe 16 supported/unsupported phenomena | Per-phenomenon error/abstention tables, candidate review queue, known/unknown alarm accounting |
| 50–100-pair natural pilot | Determine practical extraction and detection limits | Blind review sheets, reviewed precision/recall, verified findings and missed facts; otherwise descriptive coverage only |
| Small fresh-run replication | Check nondeterminism | Canonical fact/status differences, invalid-response changes |
| Serial/default/throughput calibration | Measure throughput and robustness | Cold load, first/subsequent batch times, token counts, device snapshots, semantic changes |

Run a small calibration subset before freezing the main study. Batch size 8 plus
prefix caching is an optional combined throughput profile. No speedup is assumed.
For a clean cache-only ablation, copy the default config and change only
`enable_prefix_caching`. Do not choose a profile for favorable test accuracy.

Authored probes include exact counts, preserved counts, predicate substitution,
absent NOT, quantity bounds, repeated event/count alignment, modal homographs,
negative properties, directional wrappers, unsupported role order, ambiguous
properties, chapter identifiers, Unicode evidence, currency units and conflicting
English paired with the same gloss. The builder retains no duplicate full pairs.
Expected labels are literal authored hypotheses, not extractor-generated gold,
and apply only to specified fields. There is no natural-ASL accuracy claim.

## Extra value without extra GPU inference

`analysis.json` compares CPU-English/model-gloss and model-English/CPU-gloss
hybrids, plus gold-side substitution controls when independently reviewed side
records exist. This shows which reader limits improvement and where the comparator
still abstains despite correct observations. It does not change the primary arms.
Failed model sides remain in eligible controls' denominators as UNKNOWN. Oracle
controls exclude pairs without the relevant independently annotated gold side.

Reports separate development/test/diagnostic splits, authored/human-reviewed
annotations and phenomena. They expose all alarms, rather than presenting high
precision conditional on a tiny known subset alone. The review queue includes
conflicts, newly assessed facts, approach disagreements and protocol failures;
items remain candidates until independently reviewed.

## Further experiments worth prioritizing

1. **Counterfactual independence:** conflicting English variants with an identical
   gloss. Independent gloss facts must remain source-independent; inspect direct
   judgments for unsupported reconstruction. Reuse cached identical side requests.
2. **Minimal-change stability:** controlled number/negative-marker edits; inspect
   unrelated-field changes and abstentions, not just the intended detection.
3. **Convention sensitivity:** provenance-preserving variants of documented gloss
   wrappers. Changes are diagnostic, never silently normalized into the main data.
4. **Review assistance:** measure reviewed findings and time with/without the
   review queue. Better automatic scores alone cannot establish usefulness.

Fine-tuning needs independently reviewed data. A multiple-event representation
could address the main alignment ceiling, but should be a separate diagnostic
design, not a silent expansion of the current schema. The committed CPU baseline
does not include unrelated uncommitted repair work from the original checkout.

## Validation boundary

The local host is x86 with no NVIDIA device or Docker. CPU tests, replay, baseline
audits and tokenizer-only checks cannot certify GPU throughput, memory headroom
or natural extraction accuracy. Actual DGX Spark execution remains necessary.
Memory observations are device-wide snapshots, not measured worker-model peaks.

Primary references checked during review:

- [NVIDIA single-Spark recipe](https://build.nvidia.com/spark/vllm/choose-recipe)
- [vLLM input validation](https://docs.vllm.ai/en/latest/api/vllm/v1/engine/input_processor/)
- [vLLM offline structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [vLLM prefix caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/)
