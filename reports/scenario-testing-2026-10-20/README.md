# Scenario testing and correction pilot (2026-10-20)

Aggregate results only. Sentence-level outputs contain restricted corpus text and
stay in ignored `private/`. Scripts: [`experiments/scenario-testing/`](../../experiments/scenario-testing/).
These are software and pilot measurements, not a qualified ASL evaluation.

## 1. Checker on correct references with planted errors

Reference glosses are treated as correct. Each copy gets one realistic error.
ASLLRP references (human signing, 588 pairs) carry their annotated head-shake and
topic markers from the SignStream files. ASLG-PC12 (rule-generated, English order,
1,000 pairs) has no NMM channel and writes negation as a sign. Run with the ASLLRP and
Signbank dictionaries ([`scenario-summary.json`](scenario-summary.json)).

| Planted error | ASLLRP before → now | ASLG-PC12 before → now |
|---|---|---|
| Negation dropped (sign and head-shake) | 0/119 → 113/120 | 0/110 → 110/110 |
| Negation sign added | 61/237 → 227/230 | 0/399 → 396/399 |
| Head-shake added to positive sentence | – → 404/419 | – |
| Number changed | 4/21 → 11/21 | 33/120 → 71/120 |
| Number dropped | 0/21 → 10/16 | 0/120 → 65/100 |
| Entity swapped | 0/377 → 225/377 | 0/142 → 84/142 |
| Action swapped | 0/240 → 102/240 | 0/349 → 101/349 |
| Roles reversed | 0/46 → 2/40 | 0/2 → 27/112 |

"Before" is version 0.2 (MISMATCH only); "now" counts MISMATCH or MISSING. Copies
whose construction depends on the reader differ slightly in number between runs.

Harmless edits flagged: unchanged references 0/588 and 0/1,000; hand-wrapper removal
0/303; negation kept only as a head-shake 0/114; deleting pointing signs 13/453
(this can remove the only reference to a person, so it is not always harmless).

Flags on the correct references themselves (flags / assessed checks):

| Check | ASLLRP | ASLG-PC12 |
|---|---|---|
| Entities | 101 / 512 | 110 / 964 |
| Action | 60 / 482 | 13 / 743 |
| Negation | 20 / 576 | 2 / 1,000 |
| Numbers | 3 / 10 | 1 / 33 |
| Roles | 0 / 2 | 0 / 28 |

A hand review of 30 ASLLRP entity/action flags judged about 3 to be real omissions in
the reference; the rest came from synonyms, paraphrase, classifier signs and pointing.
Many ASLG-PC12 flags are real gloss defects: 51 of the 1,000 test glosses lost the
letters "the" inside words (these → `SE`, grandmother → `GRANDMOR`, neither → `NEIR`).

English negation against the adjudicated `nmm_gold.jsonl` labels: all 84 negative
sentences were read as negative; 11 positive-labelled sentences were read as
negative, 10 of which contain a backtick contraction ("didn\`t") and are label
errors in the gold file (both annotators agree on each).

The authored cases in `authored_cases.jsonl` (written for testing, not reviewed by a
qualified ASL annotator): 1/36 false alarms on correct translations ("kids" vs
`CHILDREN`), 29/39 errors flagged without NMM labels and 37/39 with NMM labels
showing no head-shake. Still missed: "$5" vs `TEN DOLLAR`, and a role reversal
with the directional verb GIVE.

## 2. Correction pilot: can the flags improve saved translations?

**Model note.** The corrections were made by **qwen2.5 7B** running locally through
Ollama on a 16 GB laptop: a much smaller and older model than Llama 3.3 70B, which
produced the translations, and than the Qwen3.8 27B planned for the DGX Spark.

Input: the saved ASL-project run `paper_baseline_20260805T184551Z_r1` (Llama 3.3 70B,
367 ASLLRP translations with NMM labels). The checker flagged 47. For each, one
attempt per approach, scored by Sign F1 against the human reference gloss, which
neither the checker nor the corrector sees ([`correction-pilot-summary.json`](correction-pilot-summary.json)):

| Approach | Mean Sign F1 on 47 flagged (before 0.377) | Better / worse |
|---|---|---|
| No model: correct only the head-shake label when negation is flagged | 0.377 (gloss unchanged) | – |
| Same small model, generic "fix any errors" prompt | 0.408 | 17 / 16 |
| Same small model, given the checker's issues | 0.456 | 20 / 13 |

- Six flagged outputs were truncated (one or two characters). Given the issues, the
  small model re-translated all six (Sign F1 0.06 → 0.48); the generic prompt fixed five.
- On the other 41, the generic prompt lowered the mean (0.424 → 0.412) and the
  checker-guided prompt raised it (0.424 → 0.452). Head to head the guided version
  scored higher 19 times and lower 10 times (sign test p ≈ 0.14, not significant).
- The rule-only fix corrected 4 of 5 flagged head-shake labels against the human labels.
- Whole run: mean Sign F1 0.574 → 0.584 with guided corrections, 0.578 with generic ones.

One run, one small model, one attempt per pair, 47 pairs, and Sign F1 is a rough
proxy for meaning. The result is a positive but weak signal. Repeat it with the 27B
model on the Spark (run guide, section 7) before drawing conclusions.

Separately, every `paper_*` run in the ASL project has 0–22 truncated or degenerate
outputs per run (single letters, or runaway repetition such as `IXesteemesteem…`),
which also affects that project's overlap scores.
