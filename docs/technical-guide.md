# Technical guide

The [README](../README.md) contains installation instructions and runnable examples.
This guide describes the runtime, interfaces, and experiment outputs for version 0.2.0.

## Runtime

Python 3.11+ is required. The fixture path uses the standard library. Natural extraction
requires the `natural` package extra: spaCy 3.8.16, LemmInflect 0.2.3, and separately
installed en_core_web_sm 3.8.0. These run locally on CPU. No API credentials, GPU,
AMR parser, or SignON installation is needed.

The English model runs only on English. Gloss uses dictionary categories and explicit
local patterns, not an English parser or source-side hints. Missing natural tools
raise a setup error. Unsupported linguistic evidence returns UNKNOWN.

## Commands

Run `python -m signir --help` or `python -m signir COMMAND --help` for options.

| Command | Purpose | Main output |
|---|---|---|
| `demo` | Run bundled authored examples | Human-readable checks and evidence |
| `check` | Compare `--english` and `--gloss` | Text or `--json` records |
| `check-file` | Compare a JSONL file | `records.jsonl`, `checks.csv`, `manifest.json` |
| `build-controlled` | Generate 64 authored fixtures | JSONL file |
| `prepare` | Validate and group pairs before splitting | Prepared JSONL and manifest |
| `freeze` | Record experiment fingerprints and thresholds | New freeze JSON; existing freeze is not overwritten |
| `evaluate` | Evaluate prepared data against `--freeze` | Reports, evidence records, and CSV tables |
| `feasibility` | Describe supported facts without requiring gold | Coverage and evidence reports |
| `import-prior` | Join saved predictions to corpus/manifest | Private JSONL with origin hashes |
| `correct` | Replay one saved response per example | Before/after checks, improvements, regressions |

Malformed inputs, missing setup, and invalid freezes exit with status 2. A semantic
MISMATCH is a normal result, not a process failure.

## Interfaces and evidence

`signir.compare.check_pair(english, gloss)` returns two SignIR records and a `checks`
mapping. The comparator can also compare already extracted records. Each fact has a
KNOWN/UNKNOWN state, value, supporting spans, and reason. Comparisons additionally
report MATCH/MISMATCH/UNKNOWN and the assessed scope.

Evidence positions are zero-based, half-open character offsets in unchanged source
text. Keep original labels and annotation distinctions; baseline normalization is
not used to rewrite SignIR. See [schema](signir-schema.md), [input format](input-format.md),
and [architecture](architecture-overview.md).

## Evaluation and reproduction

Preparation connects shared documents, exact duplicate English, supplied duplicate
groups, and variants transitively before assigning development/test groups. Review
near-duplicates independently; exact text matching cannot identify all paraphrases.

Use a new freeze for the current code/runtime. Freeze records input/split/code hashes,
dependency versions, model/dictionary fingerprints, and development-selected baseline
thresholds. Evaluation rejects changed fingerprints. Historical reports and freezes
describe the versions that produced them, not the current checkout.

Sign F1 and word F1 compare generated gloss to a reference gloss. They require that
extra reference; the main fact checker compares English to generated gloss directly.
The saved correction experiment demonstrates plumbing only and calls no live model.

Run `python -m unittest discover -s tests -v` for the 40 software regression checks.
The [publication verification](../reports/publication-2026-10-13/verification.json)
records the commands exercised before upload. Tests and controlled fixtures do not
establish natural ASL accuracy. See [evaluation protocol](evaluation.md).

## Data handling and remaining limitations

The public repository includes authored fixtures and aggregate measurements. Keep
restricted corpora, saved natural translations, and text-bearing derived records
under ignored `private/`. Source data is not bundled, so reproducing natural results
requires separately authorized access. Follow [the data inventory](data-inventory.md).

Natural roles, broad event alignment, coreference, synonymy, and ASL grammaticality
are unresolved. Current coverage and diagnostic methods are documented in the
[natural extraction report](../reports/natural-repair-2026-10-10/README.md).
