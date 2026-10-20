# Scenario testing

Tests the rule checker on real reference glosses and on authored cases. It needs
the local `data/` folder (not distributed) and the `natural` extra.

```sh
python experiments/scenario-testing/run_scenarios.py --data data --out private/scenario-testing/run-01
```

What it measures:

1. **Reference audit.** Reference glosses (human ASLLRP, rule-generated ASLG-PC12)
   are treated as correct translations, so every MISMATCH or MISSING is a false alarm.
   ASLLRP references use their annotated head-shake/topic markers from `data/dai`.
2. **English negation** against the adjudicated ASLLRP sentence-type labels
   (`data/processed/asllrp_paper/nmm_gold.jsonl`).
3. **Corrupted references.** One realistic error per copy: changed or dropped
   number, added or dropped negation, swapped action, swapped entity, reversed
   roles. Harmless edits (unchanged, pointing/filler tokens removed, hand
   wrappers removed) are controls that should never MISMATCH. Sign F1 and word
   F1 against the original reference are reported alongside.
4. **Authored cases** in `authored_cases.jsonl`: 36 correct translations and 39
   with a known error. These glosses were written for testing and have not been
   reviewed by a qualified ASL annotator.

Outputs contain corpus text, so keep `--out` under the ignored `private/` folder.
Mutations are automatic and approximate: for example, a swapped verb may occasionally
land on a word that is not the sentence's main predicate.

For each operation, `base_any_flag` counts original pairs with an alarm,
`any_flag` counts mutated/control pairs with an alarm, and `any_new_flag` counts
pairs with an alarm on a previously unflagged check. An unchanged control has
zero new alarms even if its original already has one.

For planted errors, the historical `flagged_MISMATCH`/`flagged_MISSING` totals
count all target alarms after mutation. `target_already_flagged` exposes inherited
target alarms; `new_target_flag_rate` uses only `new_target_eligible` examples
whose target was initially unflagged. It is null when no examples are eligible.
These automatic mutations still require review before interpretation as accuracy.

The correction pilot writes an empty `records.jsonl` and a complete summary
with zero selected pairs and null averages when nothing needs correction.
It makes no inference request in that case.
