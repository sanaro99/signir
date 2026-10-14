# Corpus-pair input format (v1)

UTF-8 JSONL, one object per line. Original text is never rewritten. Only gloss
may be empty. Required fields:

```json
{"id":"example-001","english":"Alice buys 3 apples.","gloss":"fs-ALICE BUY 3 APPLE","source_group":"document-001","provenance":{"kind":"synthetic","version":"authored-v1"}}
```

`id` must be unique and stable across imports. `source_group` identifies a
document, recording session or other conservative independence unit. Supply
`document_id` and `corpus` when known. Do not invent a document ID from row order.
If document boundaries are absent, use a larger known source group and document
the reduced number of independent groups. `provenance.kind` distinguishes
`synthetic`, `saved_generated`, and other documented sources; `version` identifies
the immutable data snapshot or run. Put licences, generator/model details and
annotation conventions in provenance or the accompanying data card.

Optional fields:

| Field | Meaning |
| --- | --- |
| `reference_gloss` | Reference for overlap baselines; not a semantic gold label |
| `cohort` | `controlled`, `synthetic_reference`, `reviewed_reference`, `unreviewed_reference`, or `natural` |
| `variant_of` | Original pair ID; keeps controlled variants together |
| `duplicate_group` | Reviewed paraphrase/near-duplicate family across documents |
| `split` | Fixed `dev` or `test`; conflicts in a connected group are rejected |
| `expected` | Mapping of check names to MATCH/MISMATCH/UNKNOWN; absent = unlabelled |
| `error_type` | One primary affected check for known controlled errors |
| `change` | Original pair/gloss, modified gloss, affected check and justification |
| `review` | Reviewer ID, status, qualification and decision notes; `reviewer` required for reviewed references |
| `gold` | Independently annotated values by side and check; null means gold UNKNOWN |
| `audit` | Reviewer diagnosis with `cause` and supporting notes |

Allowed causes: `english_extraction`, `gloss_extraction`, `normalization`,
`comparison`, `unresolved`. Causes are not automatically inferred from final
checker errors. English and gloss gold should be annotated independently before
adjudicating comparisons. The gloss annotator must not use English to fill gaps.

Preparation unions shared source groups, documents, normalized exact English
duplicates, explicit duplicate groups and variant links **transitively**. A
hash of the seed and component IDs assigns unassigned components to dev/test;
the default test fraction is 0.3 and is approximate at group level. Preassigned
splits are preserved and checked. Tiny or highly duplicated datasets may have
only one split; freeze then refuses to proceed. Inspect group counts rather than
forcing row-level balance. Near-duplicate paraphrases cannot be discovered
reliably by exact matching: supply reviewed `duplicate_group` values.

The prior-study adapter expects prediction fields `source`, `reference`, and
`hypothesis`, with a run manifest. Its corpus join expects `text`, `gloss`,
`doc_id`, and optionally `sent_idx`/`source`. It imports one run at a time, hashes
all inputs, and rejects missing/ambiguous joins or duplicate generated IDs.
Model-generated `nmm` flags are not imported as independently observed signing
evidence: that would risk importing English-side guesses into gloss extraction.

Keep real corpora, annotations, generated outputs and derived evidence files in
ignored `private/`, with access governed by the original terms. Preparation and
import reject output paths equal to their input files.
