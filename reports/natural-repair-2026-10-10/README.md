# Natural-data extraction repair: results and methods

The earlier software tests did not establish real-data usefulness. Version 0.1 returned UNKNOWN for all five checks on every one of the 643 saved natural pairs. Its English grammar required one named agent and six listed verbs. Its gloss reader discarded all facts when any label was unsupported. That was a failed practical extraction design.

## What changed

Version 0.2 retains the fixture path and adds a real English dependency parser (spaCy en_core_web_sm 3.8.0), plus an independent dictionary/local-pattern gloss reader (LemmInflect 0.2.3). Gloss never receives English facts or an English parser output. Unfamiliar labels no longer discard unrelated explicit numbers or negation. Noun/verb homographs, source typos and unexplained events remain explicit uncertainties. Numbers keep their noun/unit attachment; dollars are not counted as cards. Single negated predicates can be recovered inside longer sentences without declaring the whole sentence equivalent.

## Full saved natural run

All 643 original pairs were checked before and after repair. Original generation data, manifest and corpus SHA-256 hashes remain unchanged. At least one scoped fact is now assessed in **177/643 pairs (27.5%)**, up from zero. **466/643 pairs still have all five checks UNKNOWN.** Only **206/3215 checks (6.4%)** are assessed overall.

| Check | Assessed scope | MATCH | MISMATCH | UNKNOWN |
|---|---|---:|---:|---:|
| action | One unambiguous lexical predicate | 17 | 0 | 626 |
| entities | Observed lexical mentions only | 117 | 0 | 526 |
| negation | One explicitly scoped predicate | 63 | 0 | 580 |
| numbers | Explicit numeral and its unit/label | 9 | 0 | 634 |
| roles | Explicit supported roles only | 0 | 0 | 643 |

MATCH here concerns the stated scope. No original pair is labelled as independently verified equivalent. Zero MISMATCH flags does not establish zero natural errors or a zero false-alarm rate. Natural entity matches are lexical inventories, not full entity semantics. Roles have no natural coverage. Missing numbers/negative markers cause UNKNOWN as well as genuine extraction limitations; absence of a fact is not automatically an error.

## Natural-derived diagnostic changes

Select every original pair where a numeric attachment or explicitly negative predicate was already assessed. Change only the supporting numeric span by +7, or replace NOT/NEVER with explicit POS:ACTION metadata. Separately remove the negative marker. Preserve English and all other gloss text. These are controlled copies of natural outputs, never real newly generated translations. Their provenance is labelled controlled_natural_mutation.

| Change | Number | Expected result | Obtained |
|---|---:|---|---:|
| Changed number | 9 | MISMATCH | 9/9 |
| Explicit opposite polarity | 63 | MISMATCH | 63/63 |
| Removed polarity evidence | 63 | UNKNOWN | 63/63 |

POS:ACTION is an artificial diagnostic annotation, not a standard positive ASL marker. Deletion alone must abstain. Six of nine numeric changes keep Sign F1 exactly 1.0 while the attached-number check detects the change. This illustrates observable detail beyond that baseline, not general performance superiority. The variants deliberately select recoverable facts: these scores are not a natural accuracy estimate.

## Inspection and limits

Inspected 20 evenly spaced original pairs using floor(i*642/19), i=0..19. This sample includes failures and UNKNOWNs without selection by success. Also inspected all numeric matches and every action alarm during diagnosis. Early false alarms caused by WATCH/EVEN homographs and a source typo were retained as diagnostic findings, then addressed by ambiguity abstention and dictionary-supported verb normalization. This was assistant software/lexical inspection, not independent qualified ASL review. The corpus was used in repair and is not held-out evaluation.

The all-or-nothing rejection is repaired. Broad meaning checking remains unfinished: event alignment, synonymy, bare names, compounds, directional verbs, pronouns and natural semantic roles still need a better gloss extraction method plus independent annotations. Neither a lexical MATCH nor passing these edits proves an ASL translation correct.

## Reproduction

From D:/gitgit/signir, using the project interpreter:

```powershell
.\.venv\Scripts\python.exe scripts/audit_natural_repair.py private/selected-run.jsonl --out private/natural-audit
.\.venv\Scripts\python.exe -m signir freeze reports/verification-2026-10-10/prepared.jsonl --out results/freeze-v2-new.json
.\.venv\Scripts\python.exe -m signir evaluate reports/verification-2026-10-10/prepared.jsonl --freeze results/freeze-v2-new.json --out results/controlled-v2
```

The new freeze records code, dependency versions and model/dictionary resource hashes. A deliberately changed model version in a copy of the freeze was rejected with exit 2. The original fixture results remain 20/20 introduced errors detected under a new versioned freeze; 40 software checks also pass. They are supporting regression evidence, not the natural acceptance criterion. The installed command was tested outside the repository directory on a changed currency value. The interpreter emits an existing C:/Python314 path warning; all successful runs returned exit 0.

Full sentence text and detailed results remain private locally: private/natural-repair-2026-10-10/reproduced/natural/records.jsonl, variant-records.jsonl, variants.csv and sample-audit.json. Public summaries contain aggregates only.
