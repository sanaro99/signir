# Implementation record

2026-10-10, inline execution from the user's complete staged request.

- Inspected earlier project docs, proposal text, progress notes, saved outputs,
  corpus fields, licences and baseline source. New workspace had no existing code
  or Git checkout; no branch/commit/push was attempted.
- Wrote design and implementation sequence before product code. Used the user's
  instruction to proceed through implementation without another approval round.
- Built core rules against initially failing tests, followed by data/evaluation,
  correction, and CLI tests. Fixture results use independent literal/specification
  expectations, not values produced by extractors.
- Independent code review found missing-inventory false mismatches, unaligned
  entity/count comparisons, and unsupported numeric labels which could crash.
  Added failing reproductions, fixed each, reran the complete suite.
- Added independent extraction recoverability counts; no gold means no reported
  extraction accuracy. Review confirmed the zero-coverage natural result is
  explicitly disclosed.
- Executed baseline parity, import, preparation, freeze, evaluation, correction,
  natural feasibility, wheel installation and installed-module smoke check.
  Final suite: 25 tests passing.

Material rulings:

1. Roles restricted to documented artificial metadata, because no validated
   mapping from the available natural gloss to roles was established.
2. Whole unsupported clauses/fragments abstain. Cost: zero coverage on the saved
   natural run; this is a feasibility finding, not quietly relaxed after inspection.
3. Corpus-derived text and diagnostics stay local/ignored; only synthetic records
   and safe natural aggregate metrics are included in public report paths.
4. Correction uses exact saved fixture responses because no live generator was
   verified runnable or needed for this software demonstration.
5. No qualified unchanged-reference judgments were invented. Natural false alarms
   and extraction mistakes remain unmeasured pending the annotation pilot.

## Natural extraction repair (0.2)

Fixed fixture-only blanket abstention after user identified the real-data failure. Full 643-pair diagnostic rerun: 177 pairs with at least one scoped check, 466 still entirely UNKNOWN; 206/3215 assessed checks. Nine attached-number changes and 63 explicit-polarity changes yield MISMATCH; 63 marker removals yield UNKNOWN. Six number changes remain invisible to Sign F1. Results are diagnostic, selected and not held-out accuracy. Model resources fingerprinted, original data unchanged, installed package updated to 0.2.0. New versioned freeze retains 20/20 fixture detections. See reports/natural-repair-2026-10-10/README.md.
