# Experimental event checker

The new engine replaces the single-action bottleneck with independent local-model
readers and a graph of events, participants, quantities, polarity and scope.
The legacy engine remains available for comparison. The new path does **not**
require spaCy, LemmInflect, a cloud API, or a reference translation.

A local smoke run with qwen2.5 7B through Ollama (16 authored cases) produced a
valid graph for only 2 cases; see the Spark guide, section 7.

This implementation has software tests and authored examples. It has **not**
been run against a real model or on DGX Spark. The all-UNKNOWN cases from the
legacy development corpus have not been reevaluated. Lower UNKNOWN coverage,
better accuracy, throughput, and memory use are measurements still to make in
the separate Spark workspace.

See [the validation record](event-validation.md) for executed checks and their
limits.

## Pipeline and libraries

| Module | Responsibility | Libraries |
|---|---|---|
| `events/extract.py` | Build one-source prompts; convert token spans to original character evidence | Python JSON and regex |
| `events/client.py` | Bounded Ollama/vLLM calls; detect HTTP, identity, truncation and JSON failures | Python urllib |
| `events/schema.py` | Validate event graphs, references, source spans and explicit unknowns | Pydantic 2 |
| `events/lexicon.py` | Versioned, exact corpus-label lookup with alternatives and provenance | Pydantic, JSON |
| `events/alignment.py` | Global event assignment with unmatched alternatives and ambiguity checks | SciPy, NumPy |
| `events/quantities.py` | Exact, interval and bound comparisons without floating-point rounding | Python Decimal |
| `events/compare.py` | Per-event fact checks, attached evidence and reason codes | Python |
| `events/workflow.py` | Batch errors, private artifacts, reproducibility manifests | Python |
| `events/data.py` | Event input validation and source/output alias protection | Python |
| `events/audit.py` | Paired coverage transitions; optional independent-label metrics | Python |

The model proposes interpretations. Pydantic validates their structure and
source references; it cannot establish that a predicate, role, quantity, or scope
interpretation is linguistically correct. Comparison is deterministic, but an
incorrect extraction can still produce an incorrect check.

## Install and run without a model

Use a new Linux environment, separate from the preserved Windows environment:

```sh
python3 -m venv .venv-events
. .venv-events/bin/activate
python -m pip install -e '.[events]'
python -m signir event-compare signir/fixtures/event-demo.jsonl --out private/events/demo-001
```

The saved graphs are authored examples, not model predictions or verified ASL.
They show reordered BUY events with swapped quantities, ambiguous repeated
events, a partial graph, and a conditional event. Output directories must be new.
The demo needs no model, networking, or GPU.

## Run on the separate DGX Spark workspace

Copy or check out this branch there, install the event extra, and configure the
model server in that workspace. SignIR never downloads models or launches servers.
The 128 GB unified-memory capacity alone does not establish serving speed or
the maximum practical context.

For Ollama, copy `configs/events-ollama.json` and set `model` to the **exact**
installed model tag. The included `qwen3.8:27b` is a starting candidate, not a
validated SignIR choice. Confirm context capacity and generation behavior in
the installed runtime before evaluating corpus data.

For vLLM, use the Spark-specific [NVIDIA serving recipes](https://build.nvidia.com/spark/vllm/choose-recipe)
for the selected checkpoint, quantization and container. Configure the server's
served model name to match `model`; the example `signir-reader` is a placeholder
alias. Use a server context of at least the configured `context_tokens`.
No particular checkpoint or CUDA/container combination has been tested here.

The endpoint is a base URL such as `http://127.0.0.1:8000`, without `/v1`.
If authentication is required, set `api_key_env` to an environment variable name.
Its value is read at request time and is omitted from traces. Put an immutable
checkpoint/digest and serving image identity in `model_revision` for provenance.
That field is **operator-declared**: the API response model name is checked,
but SignIR does not attest the underlying weights or hardware.

The adapters use Ollama's [JSON-schema `format`](https://docs.ollama.com/api/chat)
and vLLM's [`structured_outputs.json`](https://docs.vllm.ai/en/latest/features/structured_outputs/).
They reject redirects, incomplete responses, refusals, model-name mismatches,
duplicate JSON keys, and invalid graphs. No retries, content repairs or fallback
models are used. Proxy environment variables are ignored.

```sh
python -m signir event-check \
  --config configs/events-ollama.json \
  --english 'Alice buys 3 books.' \
  --gloss 'ALICE BUY 5 BOOK' \
  --out private/events/single-001

python -m signir event-check-file private/pairs.jsonl \
  --config configs/events-ollama.json \
  --out private/events/corpus-001
```

This sentence is an authored illustration, not a translation-quality claim.
Batch inputs use the existing pair format: `id`, `english`, `gloss`,
`source_group`, and `provenance` containing `kind` and `version`.
Neither `reference_gloss` nor existing gold/review metadata is sent to a reader.
Each side receives only its source, indexed tokens and relevant gloss lexicon
entries. A configured endpoint receives that source text; use the intended
self-hosted server for restricted data.

## Representation and conservative limits

Schema version `2.0` stores `mentions`, `events`, and `unresolved` observations.
Each mention/event has an ID, canonical label, alternatives and evidence.
Quantities refer to a participant within their event. Values are decimal
strings; relations are `eq`, `ge`, `gt`, `le`, `lt`, `range`, or `approx`.
Bounds are inclusive for `range`; `upper` is present only for ranges.
Identifiers compare as literal strings, preserving leading zeros.

Model evidence uses whitespace token indices with an exclusive end. Code
converts these to exact source slices. This avoids asking a model to calculate
character offsets. IDs, dangling references, parent cycles, invalid evidence,
non-finite quantities, reversed bounds and duplicate assignments are rejected.
Graphs are capped at 64 events and 256 mentions/unresolved observations.
Long inputs fail a conservative UTF-8-byte context budget before transmission.
That budget is a guard, not a model tokenizer or proof of server configuration.
Split long documents with preserved context rather than silently truncating them.

Alignment uses predicate and participant labels. It excludes counts, role
direction, polarity and source order. A second assignment with each selected
edge forbidden detects an equally good global interpretation. Ambiguous pairs
remain unresolved. Assignment margins are heuristic score differences, not
calibrated probabilities. Split/merged event mappings are not supported.

Within an event, unique participant labels attach quantities. Repeated
indistinguishable participants abstain. Equal numeric constraints match;
disjoint constraints conflict; overlapping non-equivalent constraints and
approximations stay UNKNOWN. There is no cross-unit conversion.

Bare gloss order cannot establish roles. Known gloss roles require explicit
annotation or resolved directional loci. Absent negation cannot establish
positive gloss polarity. These are model-declared evidence bases, not proof
that the model recognized the annotation correctly.

`roles_complete` defaults to false. Different partial role observations abstain;
a role conflict requires both events to declare exhaustive role inventories.
Equal supported role observations can match within their local scope. The
validator requires a declared complete inventory to cover each represented
participant, but this cannot prove the reader omitted no participant or role.
Completeness is another model proposal to evaluate against human annotations.

Conditional, reported, question and modal scopes, and parent links, are
represented and validated. **Only asserted, unparented events currently support
dependent role/polarity/quantity comparison.** Other contexts abstain because
matching a coarse scope label does not establish that its condition/operator
is equivalent. Lexical predicate and participant observations remain separately
visible. Missing entities or events are unresolved, not automatic omission errors.

## Corpus lexicon

Set `lexicon` in the model config to a JSON path relative to that config file.
See `signir/fixtures/event-lexicon-demo.json` for the format. Exact labels map to
one or more concepts, a kind, and provenance. Only entries present in the gloss
are sent. The bundled resource is invented demonstration data; it adds no claim
of coverage of a natural ASL corpus. A project lexicon needs reviewed senses,
variants, compounds, notation conventions and ambiguity decisions.
When an entry's kind and exact label occur in extracted evidence, validation
requires all its reviewed candidates to remain in the primary label and
alternatives. The reader cannot silently resolve reviewed polysemy. This check
does not verify which evidence span or kind the model should have selected.

## Reports and evaluation

Each run writes:

- `records.jsonl`: original sources, graphs, checks, or explicit row errors.
- `checks.csv`: per-event statuses; error rows have no fabricated check status.
- `traces.jsonl`: exact request bodies and bounded raw responses, timings and hashes.
- `summary.json`: total pairs, errors, all-UNKNOWN pairs, assessed pairs, reasons.
- `manifest.json`: source/code/schema/prompt/config/lexicon hashes, package versions,
  output hashes, configured and declared model identity.

Bundles are staged before publication, with directory/file permissions 0700/0600
on Linux. Treat them as private because they contain source text. A failed row
stays in the denominator and the command exits with status 2 after saving the
report. Invalid batch structure fails before model calls. An interrupted run
does not publish a completed bundle; there is no resume/checkpoint facility.

Saved records can be recomputed with `event-compare`. Pair audit requires exact
ID/text equality with the baseline; it does not compare raw check percentages
across different representations:

```sh
python -m signir event-audit private/events/corpus-001/records.jsonl \
  --baseline private/legacy/records.jsonl \
  --out private/events/paired-audit.json
```

Without independent labels this measures **coverage only**. Human labels are
JSONL rows with `id`, original `english`/`gloss`, nonempty `reviewer`,
`annotation_source: "independent_human"`, and a `checks` list. Each check has
`english_event`, `gloss_event`, `field`, `item` (nullable), and expected
`status`. Those four identity fields must match a saved check. A human-identified
fact absent from the output is allowed and counts as an abstention; assign it
an otherwise unused check identity. Do not derive expected labels from model
predictions. Reviewers need to inspect source facts, including missed events.

```sh
python -m signir event-audit private/events/corpus-001/records.jsonl \
  --labels private/human-event-labels.jsonl \
  --out private/events/labeled-audit.json
```

Mismatch recall includes UNKNOWNs, missing predictions and row failures as
missed errors. Precision and accuracy cover only labeled facts. Reviewer
independence is declared, not automatically verified. For architecture selection,
use a separate document-held-out sample, qualified gloss review, extraction
correctness, missed-error recall, false alarms and latency/memory. The existing
643-pair corpus is development material; lower UNKNOWN alone is insufficient.
