# Held-out fact labeling guide (heldout-v1)

This guide is for the two people labeling the sealed held-out set. Their labels are
the only independent evidence of whether SignIR-Check is right, so the process matters
as much as the labels.

## What you are judging

Each row shows one **English sentence**, one **candidate ASL gloss**, and the gloss's
**non-manual markers** (for example `negation=yes` means the signer's head-shake covers
the sentence). Some candidates are human corpus translations and some are machine
translations. You are not told which. Judge each row on its own.

For each of five fact types, decide whether the gloss keeps what the English says.
You are **not** judging grammar, naturalness or style. A free, natural ASL translation
that keeps the facts is `ok`.

| Column | Fact type | Covers |
|---|---|---|
| `entities` | People and things | Named people, places, objects, groups |
| `action` | Action | The main things that happen or are done |
| `negation` | Negation | Whether something did *not* happen or is *not* true |
| `numbers` | Numbers | Counts, amounts, ages, money, times, and what they attach to |
| `roles` | Who did what to whom | Who is the doer and who is the receiver of an action |

## Labels (use exactly one per column)

| Label | Use when |
|---|---|
| `ok` | Every English fact of this type is expressed in the gloss with the same meaning |
| `changed` | The gloss expresses a **conflicting** fact: different number, opposite polarity, a different person or thing, reversed doer and receiver |
| `omitted` | An English fact of this type is **not expressed anywhere**: not by a sign, a classifier, pointing to an established referent, or a non-manual marker |
| `added` | The gloss asserts a fact of this type that the English does not (for example a negation or a number the English lacks) |
| `na` | The English has no fact of this type, and the gloss adds none |
| `unclear` | You cannot decide, even after reading the notes below. Explain in `notes` |

If more than one label applies to a column, use the most serious: `changed` > `omitted`
> `added` > `ok`. Name the fact in `notes`, for example `numbers: 3 books -> 5 books`.

`meaning_preserved` is your overall judgment: `yes`, `partly`, `no` or `unclear`.

## Decisions that come up often

- **Synonyms and paraphrase count as expressed.** "sport" signed `COMPETITION`,
  "watch" signed `LOOK`, "need to" signed `MUST`, "don't like" signed `HATE` are `ok`.
- **Pointing and classifiers count when they clearly refer to the fact.** `IX-3p:i`
  pointing at a person already introduced expresses that person. A classifier
  predicate can express an action or an object.
- **Negation can be non-manual.** If the English is negative and the gloss has no NOT
  sign but `negation=yes`, negation is `ok`. If the English is negative,
  there is no negation sign, and `negation=no`, it is `omitted`. A negative-meaning
  sign (REFUSE, HATE, IMPOSSIBLE, FAIL) can express English negation.
- **Head-shake on a positive sentence.** If the English is positive and the gloss
  shows negation only through `negation=yes`, decide whether the head-shake
  accompanies a negative-meaning word (`ok`) or reverses the meaning (`added`).
- **Numbers must stay attached.** "3 apples" vs `APPLE THREE` is `ok`; vs `THREE
  BOOK` is `changed` for numbers (and possibly `entities`).
- **Fillers do not count.** "umm", "you know", false starts and repeated signs are
  not facts. A gloss repeating a sign is not an added fact.
- **Fingerspelling is a sign.** `fs-BOB` expresses Bob; a different fingerspelled
  name is `changed`.
- **Very loose but faithful references.** Corpus translations sometimes summarize.
  Label what the gloss actually expresses: if the English says "seven
  specialists" and the gloss shows no seven, numbers are `omitted`, even in a human
  translation.
- **Truncated or garbled gloss.** Label every missing fact `omitted`;
  `meaning_preserved` is `no`.

## Process

1. Each annotator receives only their own sheet (`sheet-A.csv` or `sheet-B.csv`)
   and this guide. Do not share or discuss labels until both sheets are complete.
   Do not look at checker output, the key file, or any run results.
2. Label every row and every column. Blank cells are rejected.
3. The coordinator runs `python -m signir heldout adjudicate` on both sheets. It
   reports agreement (per-column exact agreement and Cohen's kappa for error vs no
   error) and writes `disagreements.csv`.
4. Both annotators, or a third qualified reviewer, settle each disagreement by
   filling the `final` column, then the coordinator reruns `adjudicate` with
   `--resolved`. This writes `gold.jsonl`.
5. Freeze the checker version (commit and tag it), then run `heldout score` **once**.
   Changing rules after seeing held-out results requires a new held-out version.

Ideally at least one annotator is a fluent ASL signer or a trained ASL linguist,
and Deaf community input is sought for disputed cases. Record annotator background
(not names) in the final report.

## Coordinator commands

```powershell
# Optional: add machine translations to label alongside the references
python -m signir heldout add-candidates private/heldout-v1 --predictions <run>/predictions.jsonl `
    --system <run-name> --out private/heldout-v1/candidates-with-<run-name>.jsonl
python -m signir heldout sheets private/heldout-v1 --candidates private/heldout-v1/candidates-with-<run-name>.jsonl `
    --out private/heldout-v1/sheets
python -m signir heldout adjudicate --key private/heldout-v1/sheets/key.csv `
    --sheet private/heldout-v1/sheets/sheet-A.csv --sheet private/heldout-v1/sheets/sheet-B.csv `
    --out private/heldout-v1/adjudication-1
python -m signir heldout score private/heldout-v1 --gold private/heldout-v1/adjudication-2/gold.jsonl `
    --manifest reports/heldout-v1/manifest.json --candidates <same candidates file> --out private/heldout-v1/score-<version>
```

Translations to label must come from a generator that did not see held-out sentences
as examples. Exclude reserved groups (listed in the manifest) from few-shot pools
and retrieval indexes before generating.
