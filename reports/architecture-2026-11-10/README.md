# Architecture experiment: rules, model readers, hybrid, direct judge (2026-11-10)

**Question.** If we designed the checker from scratch, should the readers be code, a
model, a hybrid or a fine-tuned small model? We answer per fact type, and test
whether SignIR records beat a model that just sees both texts and judges directly.

Aggregates only ([`summary.json`](summary.json)); sentences stay in `private/`.
**Development data, small sample:** 45 correct ASLLRP reference translations and 130
planted variants (175 pairs). Held-out documents were refused. Treat every number as
a rough signal (counts like 2/8 have wide uncertainty).

## Arms

| Arm | What reads | What decides |
|---|---|---|
| Rules | spaCy English reader, dictionary/lexicon gloss reader | Rule comparator (today's checker) |
| Rules + embedding | Same, plus `all-minilm` similarity between unmatched English words and gloss signs | Same; a MISSING entity/action becomes MATCH above a threshold |
| Model readers | qwen3 4B reads English and gloss **separately**; quotes words, code finds positions | Simple comparator, same policy |
| Hybrid-verify | Rules; model re-reads checks with a low-confidence rule alarm | Model overrides those checks |
| Hybrid-fill | Rules; model fills checks the rules left UNKNOWN | Model fills those checks |
| Direct judge | qwen3 4B sees both texts | Model status per fact (breaks reader independence: a baseline, not a product) |

gemma3 12B was planned on a 12-reference subset but did not run: the job was stopped
when the laptop ran low on memory (the 4B model was likely still loaded alongside it).

## Results

False alarms: share of the 45 correct references with an alarm. Detection: planted
errors newly flagged on the right check (k/n, n = references not already flagged).

| Arm | False alarms (any) | Entities FA | Actions FA | Negation dropped | Negation sign added | Head-shake added | Entity swapped | Action swapped | Number changed | Number dropped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules | 24% | 9% | 18% | 11/12 | 16/16 | 30/32 | 12/25 | 2/14 | 2/8 | 2/6 |
| Rules, high confidence only | 9% | | | 8/12 | 13/16 | 0/32 | 10/25 | 2/14 | 2/8 | 2/6 |
| Rules + embedding (0.6) | 18% | 7% | 13% | 11/12 | 16/16 | 30/32 | 10/25 | 2/14 | 2/8 | 2/6 |
| Model readers (4B) | 76% | 62% | 40% | 5/6 | 14/14 | 29/30 | 8/11 | 3/10 | 5/7 | 3/5 |
| Hybrid-verify (4B) | 22% | 9% | 16% | 9/12 | 16/16 | 30/32 | 12/25 | 2/14 | 2/8 | 2/6 |
| Hybrid-fill (4B) | 49% | 24% | 20% | 7/7 | 16/16 | 32/32 | 18/22 | 5/14 | 6/7 | 3/5 |
| Direct judge (4B) | 24% | 7% | 9% | 3/12 | 1/16 | 0/32 | 6/25 | 1/14 | 6/7 | 1/5 |
| Rules + model for numbers only (post hoc, see below) | 27% | 9% | 18% | 11/12 | 16/16 | 30/32 | 12/25 | 2/14 | 6/7 | 3/5 |

The last row routes a pair to the model only when the English contains a number and
the rules' number check is UNKNOWN: 21% of pairs. Model readers and the judge gave the
same result. **This rule was designed after seeing these results on the same 45
references**, so it is a hypothesis to confirm on fresh development references, not a
measured gain.

Model readers' detection denominators are small because they already raise alarms on
most correct references; their detection rates are not comparable to the rules'.

Cost on this laptop (CPU/iGPU, no CUDA): rules take milliseconds per pair. qwen3 4B
takes about 16 s per English reading, 34 s per gloss reading and 25 s per judgment;
the strict frozen protocol (model writes character offsets) took 60 to 85 s per call
and failed validation 3 of 3 times. Lean protocol failures: 5 ungrounded quotes and 5
truncated outputs out of 176 readings.

## What we learned

1. **Negation: rules win clearly.** The 4B judge missed 9 of 12 dropped negations and
   15 of 16 added negation signs. Mostly this is a small judge approving almost
   everything: across all 175 pairs it raised only 4 negation alarms and called entities
   and actions MATCH about 90% of the time. Our judge prompt also says negation may appear
   only as a head-shake, which may make it more lenient. A larger judge may do better,
   though published work reports that model judges and learned metrics tend to
   underweight negation (NegBLEURT, ACES). Keep negation deterministic.
2. **Numbers: the model may help where the rules abstain.** The rules return UNKNOWN
   when numbers appear in natural phrasing (ages written as one sign, several numbers in
   one sentence). In 6 of 8 changed-number cases the rules abstained on the correct gloss
   too. A model reading only those cases caught 6 of 7 instead of 2 of 8, for one extra
   false alarm (post hoc; to be confirmed).
3. **Entities and actions are a word-to-sign matching problem, not a reading problem.**
   - The 4B model readers raise far more false alarms (62% on entities), mostly because
     they read corpus annotation marks as meaning (a label with a numeric suffix, like
     `GO_2`, read as the number 2) and list non-entities such as "so" and "just".
   - Generic embeddings trade detection for fewer false alarms: mother/father look alike
     to them.
   - Action swaps are mostly missed by every arm, because long glosses contain other
     signs that "cover" the English verb.
4. **Letting a model veto rule alarms hurts.** Hybrid-verify cleared 2 of the 11 true
   dropped-negation alarms and removed only one false alarm.
5. **Direct judging (at 4B) is not better.** Same false-alarm rate as the rules, much
   worse detection on everything but numbers, and no independent evidence.

## Recommendation

Rules-first, with models used **offline to build knowledge** and **online only where
the rules abstain**.

- **Deterministic core:** negation (manual and head-shake), number attachment where
  parseable, and the comparator itself. Fast, explainable, strong where it matters most.
- **Targeted model help:** independent model readers only for checks the rules leave
  UNKNOWN and that the English actually contains: numbers first (the most promising
  signal, still to be confirmed on fresh references), then entities if a larger model
  reduces false alarms.
- **The main investment is the word-to-sign lexicon** (what each gloss sign can mean),
  the source of most false alarms and missed swaps. Use a strong model offline, together
  with Sign Bank and the development corpus, to propose sign meanings; have them
  reviewed; then use them deterministically. This keeps reader independence, speed and
  auditability.
- **Fine-tuned small model: later, and narrow.** The natural target is the gloss-side
  tagger (sign to meanings, kind, number value), trained by distilling a larger model
  on development data, never held-out. Small fine-tuned checkers can be competitive
  (MiniCheck, 770M parameters, in fact checking). It needs the DGX Spark and a labeled
  slice, so it should follow a 12B to 27B run on the Spark that shows model readers
  can reach low false alarms on entities.

## Caveats

- Development data, 45 references; one ASL corpus; planted errors are word swaps, which
  favor readers that see gloss labels (the rules).
- Model readers used a simplified comparator; the rules use the full one.
- Only one model size ran. A 12B to 27B model on the Spark could change the entity
  result, so it is the most useful next measurement.

## Reproduce

```powershell
$D = "..\sign_language_gen\data"
.\.venv\Scripts\python.exe experiments/architecture/run.py sample --data $D --out private/architecture/sample.jsonl
.\.venv\Scripts\python.exe experiments/architecture/run.py models --sample private/architecture/sample.jsonl --cache private/architecture/cache-qwen3-4b.jsonl --model qwen3:4b
.\.venv\Scripts\python.exe experiments/architecture/run.py score --data $D --sample private/architecture/sample.jsonl --cache private/architecture/cache-qwen3-4b.jsonl --out private/architecture/results-NN
```

Sources: GEMBA-MQM (arXiv 2310.13988), xCOMET (arXiv 2310.10482), MetricX-25 and
GemSpanEval (arXiv 2510.24707), MiniCheck (arXiv 2404.10774), NegBLEURT (arXiv
2307.13989), ACES (arXiv 2401.16313).
