# SignIR-Check: practical design (2026-10-10)

This records the original 0.1 fixture design. Version 0.2 adds natural extraction;
see [current architecture](architecture-overview.md) and [repair design](natural-extraction-repair.md).

Independent study by Sanchit and Vedant. The intended result is an inspectable
research instrument for selected fact preservation, not an ASL translator or
grammaticality judge. The request explicitly asks for implementation after this
design; work proceeds in this session without a separate approval round.

## Immediate system

Use Python 3.11+ and its standard library, with a command-line interface. Separate
data, English extraction, gloss extraction, comparison, controlled examples,
evaluation, and correction. No model or dataset downloads are necessary.

SignIR 1.0 has five evidence-bearing fields: entities, action, negation, numbers,
and roles. Each field is KNOWN or UNKNOWN. Numbers are (entity, count) records;
negation is (action, polarity); roles are (action, agent, patient). Evidence uses
zero-based, half-open character positions in the unchanged input. Unknown fields
retain their reasons and any observations. The deterministic comparator compares
only fully known fields; missing evidence is UNKNOWN, never an automatic mismatch.
Multiplicity is preserved. Both extractors may make mistakes even though this
initial implementation also uses deterministic extraction rules.

Use a deliberately small English clause grammar and an explicit gloss vocabulary.
The two extractors have independent APIs; the gloss extractor receives no English
or English facts. Preserve the input and token positions, names, numbers, repeated
tokens, directional labels, and annotations. Unsupported forms abstain.

Gloss roles require explicit `AGENT:` and `PATIENT:` labels in a documented
**synthetic fixture annotation convention**. `NEG:ACTION` / `POS:ACTION` explicitly
scope polarity. This is test metadata written into fixture labels, not a claim
that these are standard ASL conventions. Plain gloss never supplies roles from
word order. A standalone NOT can be scoped only in the complete supported
single-action fragment; missing negation is not evidence of positive polarity.

## Feasibility and fixed source

The old project is available. Recover its Sign F1 implementation (lexical-core
multiset F1) and keep its lossy normalization strictly inside the baseline.
Select only saved run `asllrp_strat_gpt54mini_baseline_20260910T173514Z` for the
natural-output feasibility audit. Join source/reference to corpus records to
recover document IDs; reject ambiguous or absent joins. Hash inputs and preserve
provenance. Do not train or invoke a new generator.

Natural ASLLRP gloss roles, locus/coreference, classifier predicates, and
non-manual negation need a separate annotation mapping and qualified review.
Until that feasibility test succeeds, roles in natural outputs are UNKNOWN.
Measure coverage locally. Extraction accuracy on natural data remains unmeasured
until independent gold records are supplied. Do not treat corpus pairs as gold
semantic equivalence. Existing proposal language suggesting generic AMR reading
of gloss is narrowed to independent conservative extraction.

## Evaluation and correction

Generate original synthetic fixtures and one-change variants with a change log,
expected affected field, and stated justification. Explicit polarity changes,
number substitutions, entity/action substitutions and annotated role reversals
are controlled errors. Removal of a negative marker instead expects UNKNOWN.
No arbitrary shuffle is labelled meaning preserving.

Group documents, same-English duplicates, and variant families using connected
components before splitting. Tune overlap thresholds on development only; freeze
test data hashes, development hashes, source/rule hashes and thresholds before
evaluation. Refuse evaluation after any frozen input/rule changes. Separate
controlled, reviewed reference, unreviewed reference and natural cohorts.
Report correct/missed error detections, false alarms only on reviewed references,
unknown/coverage, baseline comparison, and gold extraction/audit attribution when
available. Never manufacture an extraction error attribution from a final label.

One optional correction adapter gets original English, original gloss and
diagnostics. A saved fixture-response adapter demonstrates exactly one attempt,
including a deliberate regression. Persist both outputs and both checks. No live
generator is claimed runnable; improvements are diagnostic changes only.

## Implementation sequence and acceptance

1. Add failing behavior tests for evidence spans, UNKNOWN, scoped polarity,
   number attachment, multiplicity and explicit role reversal; implement core.
2. Add validated JSONL import, provenance and leakage-resistant splitting.
3. Build controlled fixture families and documented gold extraction records.
4. Implement frozen evaluation, recovered baselines, CSV/JSON reports and audits.
5. Add one-attempt correction and CLI; test end-to-end and installation.
6. Run local data inventory and fixed-run feasibility; publish only safe aggregate
   findings. Document exact reproduction commands and unsupported phenomena.

Review focus: missing gloss, wrong-action negation, swapped number attachments,
role reversal with identical lexical overlap, transitive split leakage, changed
frozen inputs, invalid imports, and corrections which improve one check but harm
another. Keep private inputs and derived records under ignored `private/`.
