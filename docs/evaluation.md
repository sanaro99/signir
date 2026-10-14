# Evaluation protocol

## Distinct questions

1. Can extractors recover the chosen fields? Report KNOWN/UNKNOWN independently
   on each side, then compare against independent gold when supplied.
2. Given extracted records, do fixed rules produce the expected diagnostic?
3. On controlled edits, which error types are detected, missed as MATCH, or
   missed because the check is UNKNOWN?
4. On reviewed unchanged pairs, how often is an expected MATCH flagged?
5. What descriptive behavior appears on one fixed set of natural outputs?

Do not collapse these into a single accuracy number. Gold UNKNOWN is a legitimate
annotation. `wrong_known` counts asserted values that conflict with gold;
`missed_recoverable` counts abstentions on known gold. `correct` includes correct
abstentions, so always read it with `gold_unknown` and coverage.

## Freeze before evaluation

Build and review families; group by document and duplicate/variant links; assign
development/test. Select rules on development only. `freeze` fits baseline
thresholds on development rows with independently labelled errors and
synthetic/reviewed reference negatives, and writes a study lock. Error if score
is strictly below threshold. Optimize balanced accuracy, breaking ties toward
the smaller threshold (fewer alarms). Thresholds cannot flag an error whose
overlap equals 1.0. Missing references leave baselines unassessed.

The lock hashes exact data bytes, both splits and every Python module, and records
configuration, model identifiers when present, and the interpreter. `evaluate`
verifies the hashes and recalibrates on development only to catch altered lock
thresholds, then scores only test rows. Reusing test findings to change rules is
a new development cycle: version the experiment and obtain a fresh final test
set for an honest main evaluation. This initial release's test fixtures are
software acceptance cases, not an untouched future research test set.

Freeze is not tamper-proof against someone editing code, data and the lock
together. Archive/publish the lock independently before a real main test.

## Outputs and denominators

- `summary.csv`: per cohort and check, counts, coverage = (MATCH + MISMATCH)/n,
  expected-status agreement where labels exist, and false alarms with their
  reviewed-unchanged denominator. Zero reviewed examples means no measured rate.
- `controlled_errors.csv`: error type, correct detections, missed MATCH and
  missed UNKNOWN, plus each baseline's detections and assessed denominator.
  One causal edit can affect linked checks; e.g. a name change also changes a role.
- `recoverability.csv`: extraction KNOWN/UNKNOWN and coverage for each side.
  This measures willingness to extract, not correctness.
- `extraction.csv`: comparison to separately authored gold values, when available.
- `baselines.csv`: score means, number scored, number threshold-assessed/flagged,
  kept separate by cohort.
- `records.jsonl`: every result, both SignIRs, evidence, provenance and baselines.
- `report.json`: all summaries, beyond-overlap examples, audited error causes,
  and reproducibility record.

Audited causes distinguish English extraction, gloss extraction, normalization,
comparison and unresolved cases. A final wrong status alone cannot identify its
cause. Supply an `audit.cause` only after inspecting evidence and independent
gold; otherwise it remains unresolved. Gold values do not automatically justify
attributing the error to normalization rather than extraction.

Controlled fixture role labels make reversals unambiguous by construction. They
do not validate role extraction from ASLLRP. No arbitrary shuffled sequence is
used as an equivalent ASL example. Naturally annotated corpus pairs are
unreviewed references until a qualified reviewer adjudicates the selected facts.

## Feasibility and next data collection

`feasibility` performs a descriptive audit without tuning thresholds or asserting
held-out accuracy. On the selected saved run, the initial grammar provides zero
pair-level coverage. This is a failed real-data coverage feasibility test, not a
translation-quality result and not evidence that meaning is absent from ASL.

For a real term study, sample documents before rule development, ask qualified
reviewers to mark observable English and gloss facts independently, preserve
scope/locus/non-manual annotation and ambiguity, then adjudicate comparisons.
Record agreement and exclusion reasons. Recoverable natural patterns may then
be added with explicit annotations, tests and a new rule version. Keep a genuinely
new document-level final set apart from the audited material. Relationship checks
remain restricted until that evidence exists.
