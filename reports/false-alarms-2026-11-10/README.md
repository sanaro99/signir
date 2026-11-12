# False-alarm reduction and alarm confidence (2026-11-10)

Aggregate results only ([`summary.json`](summary.json)). These are **development-data**
measurements: the fixes were chosen while inspecting false alarms on these same
references, so the improvement here is optimistic. The sealed held-out set
([`../heldout-v1/`](../heldout-v1/)) is the honest test.

## What changed

- **Built-in synonym list** (`signir/lexicons/common-asl.json`, loaded by default):
  about 30 common English/ASL correspondences that differ in wording, such as sport =
  COMPETITION, watch = LOOK, need = MUST, love = KISS-FIST, kids = CHILDREN. It was
  written by the team and has not yet been reviewed by an ASL linguist.
- **Sign Bank entries** written as infinitives ("to love") and compound breakdowns
  ("ONE* (ONE+HUNDRED)") are now read instead of skipped.
- **Word family**: improvement/IMPROVE, artist/ART, coder/CODE, worker/WORK count as
  expressed. A list of look-alike words (corner is not corn+er) is excluded.
- **Fillers and pronoun forms** ("umm", "ohh", "myself", "ours") are no longer read as
  entities.
- **Names inside slash glosses** (`HANDSOME/ns-HAWAII`) and **partial fingerspelling**
  (`fs-B-U-F-F` for buffalo) count as expressed. Short letter strings that could abbreviate
  a word (`#SW` for software) make the alarm low confidence.
- **Negative-meaning signs** (HATE, IMPOSSIBLE, FAIL, REFUSE, ...) can carry an English
  "not": "don't like" signed as HATE is no longer a missing negation or missing action.
- **Confidence on every alarm** (`high`/`low`; rules in [`docs/signir-spec.md`](../../docs/signir-spec.md)).

## Results on correct reference translations (ASLLRP, 588 pairs)

Every alarm on a correct reference is a false alarm, except the few real omissions in
loose corpus translations (about 3 of 30 in an earlier hand review).

| | Before | After | After, high confidence only |
|---|---:|---:|---:|
| Pairs with any alarm | 158 (27%) | 123 (21%) | 65 (11%) |
| Entity alarms | 101 | 74 | 39 |
| Action alarms | 66 | 53 | 29 |
| Negation alarms | 20 | 16 | 5 |
| Number alarms | 2 | 2 | 2 |

With the leak-free lexicon that will be used for held-out scoring (no corpus pairs from
reserved documents): 132 pairs with any alarm, 71 high confidence.

ASLG-PC12 references (rule-generated, 1,000 pairs) are unchanged at 123 pairs, 77 high
confidence. Many of those are real defects in that corpus (for example, words that lost
the letters "the").

## Planted errors: share newly flagged (ASLLRP)

| Planted error | n | Before | After | After, high only |
|---|---:|---:|---:|---:|
| Negation sign added | 227 | 1.00 | 1.00 | 0.84 |
| Head-shake added | 416 | 0.97 | 0.95 | 0.00 |
| Negation dropped | 131 | 0.92 | 0.84 | 0.52 |
| Entity swapped | 377 | 0.51 | 0.51 | 0.44 |
| Action swapped | 240 | 0.38 | 0.35 | 0.26 |
| Number changed | 21 | 0.52 | 0.52 | 0.52 |
| Number dropped | 16 | 0.56 | 0.56 | 0.56 |
| Roles reversed | 42 | 0.05 | 0.07 | 0.00 |

Unchanged controls still raise zero new alarms. Head-shake-only negation is low
confidence by design: in human signing a head-shake also marks doubt or correction.
Use `all alarms` for recall-oriented review and `high confidence` for a short,
precise review queue.

## Reproduce

```powershell
$D = "..\sign_language_gen\data"
.\.venv\Scripts\python.exe experiments/scenario-testing/run_scenarios.py --data $D --out private/scenario-testing/run-NN `
    --gloss-lexicon $D/processed/asllrp/gloss_dictionary_merged_translations.json `
    --gloss-lexicon $D/export/signbank_translations_2026_08_02.lexical.json
```

Add `--no-builtin-lexicon` to reproduce the "before" lexicon setup (the "before" run also
used the v0.2 code from commit `d05fc19`).
