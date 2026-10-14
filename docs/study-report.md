# Initial implementation and feasibility report

2026-10-10. Independent study by Sanchit and Vedant. Software version 0.1.0;
SignIR version 1.0. These are results of executed software demonstrations and
one local feasibility audit, not a completed natural-ASL validation study.

## What ran

- The package was built as a wheel and installed into a local virtual environment.
  An isolated interpreter imported it from `site-packages` and ran a number check.
- All 25 tests passed, including full CLI preparation/freeze/evaluation/correction,
  absent evidence, wrong negation scope, number attachments, explicit role reversal,
  split leakage, changed frozen data, and single-attempt correction regressions.
- The original Sign F1 pure functions ran on 643 saved pairs plus four edge cases.
  The recovered implementation agreed exactly on all 647 comparisons.
- The controlled evaluation ran after freezing data/rules and development-selected
  thresholds. All input/output artifacts are local and reproducible.
- The selected 643 earlier generated outputs imported successfully with document
  IDs recovered by exact source/reference joins. Original corpora were unmodified.

## Controlled software demonstration

64 authored examples, eight source families: 32 development and 32 test examples.
The test set contains eight synthetic references, 20 explicit errors (four per
type), and four removed-negation-marker cases whose correct result is UNKNOWN.
Fixture annotations explicitly encode roles/polarity; they are not natural ASL.

| Error type | Checker detected / total | Sign F1 detected / total | Raw word F1 detected / total |
| --- | --- | --- | --- |
| Entity | 4 / 4 | 0 / 4 | 4 / 4 |
| Action | 4 / 4 | 4 / 4 | 4 / 4 |
| Explicit polarity | 4 / 4 | 4 / 4 | 4 / 4 |
| Number | 4 / 4 | 0 / 4 | 4 / 4 |
| Annotated role reversal | 4 / 4 | 0 / 4 | 4 / 4 |

The development thresholds were approximately 0.9 for Sign F1 and 0.916667 for
raw word F1, with error defined as score strictly below threshold. These fit
28 labelled development rows; removed-marker cases were excluded from binary
baseline fitting. Exact values and hashes are in
[`reports/controlled-v1/freeze.json`](../reports/controlled-v1/freeze.json).

All 160 expected check statuses in the 32 test examples were reproduced. Of those
statuses, 20 were UNKNOWN, so pair/check coverage was 140/160 = 87.5%. The 20
primary explicit errors were detected; none were missed as MATCH or UNKNOWN.
All four removed-marker examples correctly abstained on polarity. All 320
side/check gold values matched the authored fixture specifications, with zero
wrong-known values or missed recoverable values.

These numbers establish implementation behavior only. Gold was authored from
the same limited fixture specification used to build examples, independently of
the extraction functions, without qualified natural-ASL review. Test families
share the development grammar. This is not evidence of corpus generalization,
and 100% specification agreement should not be presented as research accuracy.

There were no MISMATCH results on the eight unchanged synthetic examples. There
were **zero qualified reviewed unchanged natural examples**, so no natural false
alarm rate was measured. The error-attribution map is empty because no fixture
status disagreed with its specification; natural error causes remain unmeasured.

Twelve explicit errors had Sign F1 1.0 while the checker identified their changed
facts. Numbers disappear under the old lexical-core function, and synthetic
annotation wrappers also interact with its lossy normalization. These findings
demonstrate concrete metric limitations within these fixtures. Raw word F1
detected all 20 errors here, so **this test does not show a detection advantage
over that baseline**. The checker additionally identifies the affected fact and
supporting spans rather than only reporting an overlap score.

## Natural-output feasibility: not yet useful

Fixed saved run: `asllrp_strat_gpt54mini_baseline_20260910T173514Z`, containing 643
outputs and 15 source documents. The manifest records `gpt-5.4-mini`; the model
was not called. New checker preparation produced 453 development and 190 test
rows, preserving all 15 document groups. The descriptive feasibility audit used
all 643 rows; it was not a main held-out accuracy evaluation.

**Every fact on both extraction sides was UNKNOWN in all 643 cases.** Pair-level
coverage was consequently 0/643 for each of the five checks. The restricted
English grammar and complete-fragment gloss vocabulary did not cover these
natural inputs. This is a negative feasibility finding about this implementation,
not evidence that the corpus or ASL lacks the relevant meaning.

No independently annotated SignIR gold was available for these outputs, so
extraction accuracy, natural error detection, false alarms and causal error
attribution cannot be estimated. No synthetic threshold was applied to natural
outputs. Descriptive means against reference gloss were Sign F1 0.545967 and
raw word F1 0.378045; these are overlap scores, not semantic-quality estimates.

The next research step is a qualified annotation/feasibility pilot followed by
validated broader English and corpus-specific gloss extraction. Natural roles
remain unsupported until explicit annotation evidence can be mapped. The saved
correction adapter provides a workflow demonstration, not a live generator.
No natural-ASL improvement conclusion is supported by this release.

## One-attempt correction demonstration

Two authored saved responses were replayed after evaluation. Each adapter was
called once. The first changed a wrong count to the expected count. The second
also fixed a count but replaced the person, recording a number improvement and
an entity regression. Both original and corrected outputs and checks are saved
locally in `results/correction-v1/`. These are fixture behaviors, not generated
experimental results or evidence that corrected ASL is better.

## Reproduction and artifacts

Follow the exact commands in the [README](../README.md). The public
[`reports/controlled-v1/`](../reports/controlled-v1/) contains synthetic-only CSV,
JSON evidence, and the frozen record. [`reports/natural-feasibility.json`](../reports/natural-feasibility.json)
contains safe aggregates and reproducibility hashes only. Corpus-derived text
stays in ignored `private/`. The [inventory](data-inventory.md) records remaining
licence and annotation issues, and [baseline parity](baseline-parity.json) records
the recovered source hash and executed comparison count.

The local Windows sandbox initially blocked its default temporary folder during
tests/virtual-environment bootstrapping. Test temporary directories were placed
inside the workspace; packaging used a workspace-local temporary folder. No
product dependency or model download was required. A shell/Python path warning
appeared in this host, but verification commands completed successfully.

## Superseding extraction repair, package 0.2

The earlier all-UNKNOWN audit was a failure of the overly restricted extraction design. It did not establish practical usefulness. The repair now assesses scoped facts in 177/643 natural pairs, with 117 lexical entity inventories, 17 single predicates, 63 explicitly negated predicates and nine numeric attachments. Natural roles still have zero coverage. See [the new diagnostic report](../reports/natural-repair-2026-10-10/README.md). This is the same diagnosis corpus, not a new held-out study or measured natural accuracy. Original historical reports and freezes remain intact.
