# CLAUDE.md

Guidance for AI assistants and new contributors. Read this before changing code or docs.

## What this project is

**SignIR** is a structured, JSON intermediate representation (IR) of the *facts* in one
English sentence/clause or one written ASL gloss: who/what is involved, the action, whether
it is negated, attached numbers, and supported roles, each with exact evidence spans and an
explicit UNKNOWN state.

**SignIR-Check** (the package, `signir-check` 0.2.0) uses that IR to audit English → ASL
gloss translations. English and gloss are read **independently** into SignIR records, then
a **deterministic** comparator returns MATCH / MISMATCH / MISSING / UNKNOWN per fact, with
reasons and evidence.

Why it exists: the earlier study (`../sign_language_gen`, an LLM text-to-gloss reproduction
of Zhang et al. CHI 2025) scored outputs with BLEU and Sign F1. Overlap metrics miss the
errors that matter most for Deaf readers. A changed number, a dropped negation or swapped
roles can still score Sign F1 = 1.0. SignIR makes those errors visible and explainable.

Independent study (UW, Sanchit and Vedant; advisor "Professor Mike", whose DGX Spark is the
GPU target). Background framing: AMR and the SignON InterL representation. The novelty is
**not** "an IR between English and gloss" (SignON/AMR already exist). It is evidence-bearing,
independently derived fact records that can **detect, and maybe help repair**, meaning
errors in generated gloss.

### Scope (do not cross without discussion)
- In scope: written English and written gloss, selected facts, evaluation and one-pass repair.
- Out of scope: generating ASL, judging signing video, certifying ASL grammar or naturalness.
  A MATCH applies only to the stated fact and scope. It does not mean "good ASL".

## Two directories

- `D:\gitgit\signir`: **this repo, the working project.** Make changes here.
- `D:\gitgit\sign_language_gen`: the earlier project. Treat it as **read-only**: a source of
  restricted data (`data/`), saved generation runs (`results/`), the original Sign F1 code,
  and proposal scripts (`scripts/build_signir_*.py`). Do not edit it unless asked.

## One representation, two comparators

**SignIR 2.0 is the canonical format** (`docs/signir-spec.md`, `signir/events/schema.py`,
JSON Schema `schemas/signir-2.0.schema.json`; regenerate with `scripts/export_schema.py`,
a test fails when it drifts). Both comparators follow the same policy and return the
same contract: MATCH / MISMATCH / MISSING / UNKNOWN, and `confidence` high/low on every
alarm (null otherwise).

| | Rule checker (default) | Event engine (experimental) |
|---|---|---|
| Record | SignIR 1.0 fact card + reader analysis block (`schema.py`, `natural.py`) | SignIR 2.0 graph |
| Readers | Fixture grammar, spaCy English, dictionary/LemmInflect gloss | CPU rule readers (`events/from_rules.py`) or local model via Ollama/vLLM (`events/extract.py`) |
| Compare | `compare.py` (one check per fact type) | `events/alignment.py` + `events/compare.py` (per-event checks) |
| CLI | `check`, `check-file`, `ir`, `prepare`, `freeze`, `evaluate`, `correct`, ... | `event-check --engine rules\|model`, `event-check-file`, `event-compare`, `event-audit` |

The rule checker stays the default until a held-out evaluation shows the event engine
is at least as good. `signir/gpu/` is the frozen DGX Spark experiment harness on 1.0
five-field records (arms `cpu`, `structured`, `judge`); leave it unchanged so its runs
stay comparable.

Lexicons: `signir/lexicons/common-asl.json` is built in and loaded by default.
`--gloss-lexicon PATH` adds dictionaries, `--no-builtin-lexicon` drops the built-in one,
`lexicon.configure([])` disables all (tests use this).

## Held-out evaluation (do not contaminate)

`reports/heldout-v1/manifest.json` reserves 165 document groups; the 150 sealed pairs
live in `private/heldout-v1/`. **Never read, tune on, or build lexicons/prompts/few-shot
pools from reserved groups.** Develop on `asllrp/test`, `asllrp_paper/test`,
`asllrp_strat/test` (already used). For held-out scoring use a lexicon from
`scripts/build_lexicon.py` (the old corpus dictionary contains reserved documents).
Score once per tagged checker version (`python -m signir heldout score`). Labeling
protocol: `docs/annotation-guide.md`.

## Commands (Windows, from repo root)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests        # ~176 tests, ~35 s
.\.venv\Scripts\python.exe -m signir demo
.\.venv\Scripts\python.exe -m signir check --english "Alice buys 3 apples." --gloss "fs-ALICE BUY 9 APPLE" [--json] [--gloss-nmm negation=false] [--notation aslg_pc12]
.\.venv\Scripts\python.exe -m signir check-file signir/fixtures/demo.jsonl --out results/demo-checks
.\.venv\Scripts\python.exe -m signir ir --english "Alice buys 3 apples." --gloss "fs-ALICE BUY 9 APPLE"
.\.venv\Scripts\python.exe -m signir event-check --engine rules --english "..." --gloss "..." --out private/events/run-NN
.\.venv\Scripts\python.exe -m signir event-compare signir/fixtures/event-demo.jsonl --out private/events/demo-NNN
.\.venv\Scripts\python.exe experiments/scenario-testing/run_scenarios.py --data ..\sign_language_gen\data --out private/scenario-testing/run-NN `
    --gloss-lexicon ..\sign_language_gen\data\processed\asllrp\gloss_dictionary_merged_translations.json `
    --gloss-lexicon ..\sign_language_gen\data\export\signbank_translations_2026_08_02.lexical.json
```

- `.venv` is Python 3.14 with the `natural` and `events` extras and `en_core_web_sm` 3.8.0.
- Three tests (`*alias*`/symlink tests in `test_event_workflow`, `test_gpu_runner`) error on
  Windows without Developer Mode (WinError 1314, symlink privilege). This is an environment
  issue, not a regression. They pass on Linux.
- Output directories must be **new**. Most commands refuse to overwrite.
- Tests use stdlib `unittest`, not pytest.

## Rules that must be followed

1. **Extractor independence.** The gloss reader never sees English, English facts, the
   reference gloss or comparison results, and vice versa. This is the core validity claim.
2. **Missing evidence is UNKNOWN, never MISMATCH.** An absent NOT is not positive polarity
   (negation may be a non-manual head-shake). Gloss word order is weak role evidence
   (low-confidence alarms, never with a topic marker). MISSING means the English states a
   fact and the gloss, including annotated non-manual markers, shows no trace of it.
   Keep both comparators on this shared policy; change them together.
3. **Evidence spans** are zero-based, half-open Unicode character offsets into the unchanged
   text. `text[start:end] == span.text` must hold.
4. **Restricted data stays private.** ASLLRP/NCSLGR/Signbank text, saved natural translations
   and sentence-level results go only in gitignored `private/` (or `results/`, `data/`).
   Public `reports/` contain aggregates and authored/synthetic examples only.
5. **Claims discipline.** Coverage is not accuracy. The 643-pair ASLLRP run and the scenario
   data were used during development, so they are not held-out. No accuracy claim without
   independent human labels on an untouched, document-held-out sample. Report MISSED and
   UNKNOWN in denominators. Authored fixtures are not natural ASL.
6. **Freeze before evaluation.** `freeze` hashes data, splits, code and thresholds, and
   `evaluate` refuses changed inputs. Changing rules after seeing test results starts a new
   development cycle with a new freeze.
7. **No silent fallbacks** in model paths: no retries, no repair of model output, no CPU
   fallback for GPU runs. Failed rows stay in denominators and are distinct from UNKNOWN.
8. **Add a failing test first** for any bug fix or new extraction pattern.
9. Work on `feat/<thing>` branches and PR into `main`. Keep `main` runnable.

## Where things are

- `README.md`: public overview and current results.
- `docs/signir-spec.md`: **the format and check-contract reference** (1.0 and 2.0).
- `docs/architecture-overview.md`, `docs/event-checker.md` (model readers, Spark setup).
- `docs/evaluation.md`: evaluation questions, freeze protocol, output files.
- `docs/data-inventory.md`: what data exists in `../sign_language_gen` and its licence limits.
- `reports/false-alarms-2026-11-10/`: latest development measurements (false alarms, planted errors, confidence).
- `reports/heldout-v1/`: the sealed held-out set and its protocol.
- `reports/scenario-testing-2026-10-20/`: earlier scenario results and the correction pilot.
- `reports/natural-repair-2026-10-10/`: v0.2 coverage on 643 natural pairs (177 assessed, 466 all-UNKNOWN).
- `docs/study-report.md`, `docs/work-log.md`: history and rulings.
- `.code-review-graph/`: local code graph used by the explore/review skills (not project code).
