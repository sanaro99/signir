# Sealed held-out set heldout-v1

[`manifest.json`](manifest.json) seals a document-held-out set for independent human
labels. It lists reserved document groups, counts and SHA-256 hashes, never sentence
text. The pairs themselves are restricted corpus data and stay in `private/heldout-v1/`.

- **150 pairs** from **40 document groups**: 45 ASLLRP (the only 2 ASLLRP documents
  that no SignIR development step read) and 105 NCSLGR (never used by SignIR).
- Stratified by simple English cues: 46 contain a negation word, 29 a number, 75 neither.
- All 150 have annotated non-manual markers (negation, topic) from the corpus files.
- **165 groups (1,507 sentences) are reserved.** Do not use them for rule, lexicon,
  prompt or few-shot development. `experiments/scenario-testing/run_scenarios.py`
  refuses reserved documents. `scripts/build_lexicon.py` builds a lexicon without them.

## Protocol

1. Optionally add machine translations from a generator that never saw reserved
   sentences (`heldout add-candidates`).
2. Produce blind sheets (`heldout sheets`). Two annotators label independently,
   following [`docs/annotation-guide.md`](../../docs/annotation-guide.md).
3. Check agreement and settle disagreements (`heldout adjudicate`), producing `gold.jsonl`.
4. Commit and tag the checker version, then score **once** (`heldout score`). The
   report gives precision, recall (UNKNOWN counts as a miss), false-alarm rate and
   coverage per fact type, for all alarms and for high-confidence alarms, with 95%
   intervals.

Rebuilding with the same data, seed and code reproduces the same hashes. Any change
after scoring needs a new version (`heldout-v2`) drawn from still-unused documents.
