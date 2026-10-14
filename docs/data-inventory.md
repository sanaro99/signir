# Available-material inventory, 2026-10-10

Inspected read-only: `../sign_language_gen`, `../sign_language_gen_data_export`,
and `../_paper_internal_20260812`. The new `signir` directory was empty; no
applicable repository AGENTS.md files were found. The prior README, dataset
documentation, licence, proposal-builder source and progress note were read.
No original data was changed, downloaded or copied into distributable fixtures.

`inventory-metadata.json` contains locally measured counts, keys, hashes, missing
document IDs and repeated-English counts for 20 selected files. It contains no
corpus sentences/glosses. The earlier data export is a mirror, not an independent
sample. Do not merge it into a second dataset.

| Local material | Content and useful fields | Licence/access recorded in local documentation | Interpretation and gaps |
| --- | --- | --- | --- |
| `sign_language_gen/data/processed/{example_pool,test}.jsonl` | 20,000 / 1,000 records; English `text`, `gloss`, `source` | ASLG-PC12: no known licence; redistribution not assumed | Automatic text-transformation pseudo-gloss, not natural signing annotation; source document boundaries need inspection |
| `data/processed/asllrp_strat/{example_pool,test}.jsonl` | 1,249 / 643; `text`, `gloss`, `doc_id`, `sent_idx`, `source` | ASLLRP: research/education access restrictions; no redistribution without permission | Naturally annotated signing references; only one selected saved generator run used |
| `data/processed/asllrp/`, `asllrp_paper/`, `asllrp_doc_faithful/` | Alternate splits: 2,066/220, 1,472/368, 1,587/248 | Same corpus restrictions | Overlapping views, not independent corpora. Earlier notes document sentence-level near-duplicate leakage and signer/session effects |
| `data/processed/ncslgr/` | 1,432 pool / 249 test; document/story provenance | No clear broad redistribution grant in inspected docs; handle as local research corpus | Naturally annotated signing from the ASLLRP family; may overlap other BU material |
| `data/dai/` and export mirror `data/dai/*.xml` | Original annotation collections; file stems contribute to document identity | Access-controlled ASLLRP terms in earlier documentation | Primary checkout has no loose XML files in this directory; the export mirror supplies XML. Linguistic/tier information may exist beyond flattened text; preserve filenames |
| `data/raw/ncslgr/` | ELAN annotations; main gloss, English translation and NMM tier information described by loader docs | Same cautious local-use treatment | Negative/head-motion/time-aligned tiers need proper scope mapping; not a ready text polarity oracle |
| `data/signbank/*.csv` | Dictionary/citation forms, not sentence-level translations | ASLLRP Sign Bank restrictions | Could help label mapping after annotation review; no sentence-equivalence gold |
| `data/asl_lex/*.csv` | Lexical metadata | Earlier documentation reports CC BY-NC | Not parallel sentence data; attribution/noncommercial constraints reported |
| `data/asl_citizen/*.csv` | Isolated-sign metadata, no sentence pairs | Earlier documentation reports Microsoft Research License, no redistribution | No need for videos in this project; no large archive opened/downloaded |
| `data/processed/probes*/` | 126 probe examples per view, plus duplicated pools | Keep local unless independently cleared | Manually designed probe content; not an additional independent natural corpus |
| `data/processed/nmm_gold*.jsonl`, `data/annotations/` | Existing NMM gold/pilot sheets; 400 and 369 records | Inherit source/review constraints | English-side and signing-side polarity must be distinguished; no unexamined label reused as gloss evidence |
| `results/asllrp_strat_gpt54mini_baseline_20260910T173514Z/` | 643 `source`, `reference`, `hypothesis` outputs, generated `nmm`; run manifest | Corpus-derived material kept private | Fixed source for this feasibility audit; predictions lack doc IDs, restored by exact unambiguous join |
| `sign_language_gen_data_export/data/` | Mirrored DAI, processed data, lexicons, annotations | README explicitly says bundle is not redistributable | Duplicate storage; never counted twice |

The selected run manifest records model label `gpt-5.4-mini`, provider Azure,
temperature 0, seed 7, eight static shots, and prompt hash `f6bc4b6880ce`.
These are historical manifest values, not a claim about current model availability.
No generation endpoint was tested. Saved outputs and recovered baseline pure
functions were actually run through this project's import/evaluation paths.

References inspected locally:

- `sign_language_gen/README.md`, `docs/datasets.md`, `LICENSE`.
- `sign_language_gen_data_export/README.md` (explicitly prohibits sharing bundle).
- `sign_language_gen/scripts/build_signir_prof_mike_proposal.py` (proposal content).
- `_paper_internal_20260812/progress_update_2026-08-12.md` (earlier metrics and leakage concerns).
- `sign_language_gen/src/aslgloss/evaluation/sign_selection.py` (executed for parity).

The licence descriptions above report what those local records say; they are not
new grants or a legal determination. Consult the actual access agreement before
sharing any corpus. Public URLs in the old documentation do not establish rights.

## Remaining real data requirements

Independent reviewer gold for English facts and observable gloss facts, with
scope/role evidence and UNKNOWN labels; a documented mapping for natural gloss
annotation conventions; reviewed unchanged controls; adjudicated generated errors;
duplicate/paraphrase groups across documents; and a new frozen final set after
feasibility. These are absent from the current checker-specific materials.
General gloss vocabulary and unrestricted English parsing also require validation.
Until then, the released program supports controlled research plumbing and exposes
the feasibility gap; it cannot substantiate natural ASL accuracy claims.
