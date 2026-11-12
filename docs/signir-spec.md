# SignIR specification

**SignIR is a structured, evidence-bearing record of the facts in one English text or
one written ASL gloss.** It lists who and what is involved, what happens, whether it
is negated, the quantities and what they attach to, and who does what to whom. Every
value points to the exact source text that supports it, and anything the reader
cannot establish is recorded as unknown or unresolved rather than guessed.

This document is the single reference for the format and for the check results built
on it. It supersedes the version notes in `signir-schema.md` (1.0) and
`event-architecture.md` (2.0).

## Versions and who uses them

| Version | Status | Shape | Producers | Consumer |
|---|---|---|---|---|
| **2.0 graph** | **Canonical.** New work targets this format. | Mentions, events, quantities, scope, non-manual markers, unresolved items (`signir/events/schema.py`, JSON Schema in `schemas/signir-2.0.schema.json`) | CPU rule readers (`signir/events/from_rules.py`), local model readers (`signir/events/extract.py`), saved graphs | Event comparator (`signir/events/compare.py`) |
| **1.0 fact card** | Legacy, still the default checker (`signir check`) | Five fixed fact fields plus a reader analysis block (below) | Fixture and natural rule readers (`english.py`, `gloss.py`, `natural.py`) | Rule comparator (`signir/compare.py`), DGX Spark experiment |

The two comparators follow the **same policy** (next section) and return the **same
check contract**. The rule comparator stays the default because it is the one with
measured behavior on real data. The event comparator becomes the default only after
a held-out evaluation shows it is at least as good.

`signir/gpu/` is a frozen experiment harness, not a third engine. Its prompts ask
models for 1.0 five-field records and its freeze hashes them, so it is left unchanged
to keep its runs comparable. It reuses the 1.0 comparator in its original
three-status mode.

## Shared policy (both engines)

1. **Independent readers.** The gloss reader never receives the English, English
   facts, a reference gloss or a comparison result, and vice versa. The gloss's own
   non-manual labels are part of the gloss and may be given to the gloss reader.
2. **Missing evidence is UNKNOWN, not MISMATCH.** An absent NOT is not positive
   polarity, because negation can be a non-manual head-shake.
3. **MISSING** means the English states the fact and the gloss shows no trace of it,
   including through its annotated non-manual markers. Negation is MISSING only when
   the negation marker is annotated as absent (`negation=false`), or for English-order
   gloss notation (ASLG-PC12), which always writes negation as a sign.
4. **Roles from gloss word order** are accepted only for a plain lexical verb, never
   with a topic marker or a directional (locus) verb. They are weak evidence, so any
   role conflict based on them is a **low-confidence** alarm.
5. **Head-shake without a sign** on a positive English sentence is a low-confidence
   MISMATCH, because head-shakes also mark doubt, correction and emphasis.
6. **Synonyms and word family** (lexicon entries, improvement/IMPROVE) can show that
   something is expressed, so they prevent MISSING. They never establish equality
   for MATCH or MISMATCH by themselves in the event comparator.
7. Evidence offsets are zero-based, half-open Unicode character positions into the
   unchanged source: `text[start:end] == span.text`.

## The 2.0 graph

Top level: `version` (`"2.0"`), `language` (`english` or `gloss`), unchanged
`text`, `mentions`, `events`, `unresolved`, and, for gloss only, `nonmanual`.

| Object | Fields | Notes |
|---|---|---|
| Mention | `id`, `label` (lowercase lemma), `kind` (person, thing, place, time, other), `form`, `alternatives`, `concepts`, `evidence` | `form`: lexical, name, fingerspelled, pointing, classifier, pronoun. `alternatives` are competing readings (ambiguity). `concepts` are synonyms/word-family words it can express |
| Event | `id`, `predicate`, `form`, `alternatives`, `concepts`, `evidence`, `participants` (mention IDs), `roles`, `roles_complete`, `polarity`, `scope`, `quantities` | `form`: lexical, classifier, directional, fingerspelled |
| Role | `role` (agent, patient, recipient, experiencer, location, instrument), `mention_id`, `basis`, `evidence` | `basis`: syntactic (English), word_order, explicit_annotation, resolved_locus (gloss) |
| Polarity | `value` (positive, negative, unknown), `basis`, `evidence` | `basis`: syntactic, explicit_annotation, lexical_negator, nonmanual, unknown |
| Scope | `kind` (asserted, conditional, question, reported, possible, obligatory, unknown), `parent_event`, `evidence` | Only asserted, unparented events support dependent comparisons |
| Quantity | `mention_id`, `kind` (count, money, duration, age, identifier, other), `unit`, `value` (decimal string), `relation` (eq, ge, gt, le, lt, range, approx), `upper`, `evidence` | Quantities attach to a participant of their own event |
| NonManual | `label` (negation, topic, yes_no_question, wh_question, conditional), `value` (true/false), `evidence` | `false` means annotated absent; a label that is not listed was not supplied |
| Unresolved | `reason` (lexical_ambiguity, unsupported_scope, unresolved_role, unresolved_reference, unresolved_quantity, unparsed_content), `detail`, `evidence` | Anything a reader saw but could not place |

Validation (`Graph.model_validate`) rejects: unknown fields, unsupported versions,
duplicate or dangling IDs, parent cycles, evidence that does not match the source,
known polarity or scope without evidence, incoherent or non-finite quantities, and
these gloss/English rules:

- English graphs carry no non-manual markers, no word_order or resolved_locus roles,
  no nonmanual polarity and no sign forms.
- Gloss roles cannot be `syntactic`. `word_order` roles need a lexical event and no
  topic marker.
- Gloss positive polarity needs `explicit_annotation` or `nonmanual` with
  `negation=false`. `nonmanual` polarity must agree with the negation marker.
- A declared complete role inventory must cover every participant.

### Example: English

`python -m signir ir --english "Alice buys 3 apples."` (shortened):

```json
{"language": "english", "text": "Alice buys 3 apples.",
 "mentions": [{"id": "m0", "label": "alice", "kind": "other", "form": "name", "evidence": [{"start": 0, "end": 5, "text": "Alice"}]},
              {"id": "m3", "label": "apple", "kind": "thing", "concepts": ["apples"], "evidence": [{"start": 13, "end": 19, "text": "apples"}]}],
 "events": [{"id": "e0", "predicate": "buy", "participants": ["m0", "m3"],
             "roles": [{"role": "agent", "mention_id": "m0", "basis": "syntactic", "evidence": ["..."]},
                       {"role": "patient", "mention_id": "m3", "basis": "syntactic", "evidence": ["..."]}],
             "roles_complete": true,
             "polarity": {"value": "positive", "basis": "syntactic", "evidence": [{"start": 6, "end": 10, "text": "buys"}]},
             "scope": {"kind": "asserted", "evidence": ["..."]},
             "quantities": [{"mention_id": "m3", "kind": "count", "unit": "item", "value": "3", "relation": "eq",
                             "evidence": [{"start": 11, "end": 12, "text": "3"}]}]}],
 "unresolved": []}
```

### Example: negation by head-shake

`python -m signir ir --gloss "fs-BOB LIKE DOG" --gloss-nmm negation`. There is no NOT sign; the
head-shake marker carries the negation:

```json
{"language": "gloss", "text": "fs-BOB LIKE DOG",
 "events": [{"id": "e0", "predicate": "like", "participants": ["m0", "m2"],
             "roles": [{"role": "agent", "mention_id": "m0", "basis": "word_order", "evidence": ["..."]},
                       {"role": "patient", "mention_id": "m2", "basis": "word_order", "evidence": ["..."]}],
             "polarity": {"value": "negative", "basis": "nonmanual", "evidence": [{"start": 7, "end": 11, "text": "LIKE"}]},
             "scope": {"kind": "asserted", "evidence": ["..."]}, "quantities": []}],
 "nonmanual": [{"label": "negation", "value": true}]}
```

With `negation=false` the same gloss gets positive `nonmanual` polarity. Compared with
"Bob does not like dogs.", that is a high-confidence **MISSING** negation.

### Example: topic marking and pointing

`python -m signir ir --gloss "IX-3p:i STUDENT HELP TEACHER" --gloss-nmm topic`. The
topic marker can front the object, so no word-order roles are recorded. The pointing
sign is a mention with `form: pointing`:

```json
{"mentions": [{"id": "m1", "label": "student", "kind": "thing", "evidence": ["..."]},
              {"id": "m3", "label": "teacher", "kind": "thing", "concepts": ["teach"], "evidence": ["..."]},
              {"id": "m0", "label": "ix-3p:i", "kind": "other", "form": "pointing", "evidence": ["..."]}],
 "events": [{"id": "e0", "predicate": "help", "participants": ["m1", "m3"], "roles": [],
             "polarity": {"value": "unknown", "basis": "unknown", "evidence": []}, "...": "..."}],
 "nonmanual": [{"label": "topic", "value": true}]}
```

A classifier predicate is an event with `form: classifier`; a classifier standing for
an object is a mention with `form: classifier`. When a gloss contains pointing,
classifier or pronoun mentions, a participant missing from the gloss is a
low-confidence alarm, because it may be referred to without a name.

## Check-result contract

| Status | Meaning |
|---|---|
| MATCH | Both sides state the fact and agree, within the stated scope only |
| MISMATCH | Both sides state the fact and conflict |
| MISSING | The English states it; the gloss, including annotated non-manual markers, shows no trace |
| UNKNOWN | Not enough evidence either way. Never counted as an error, and counted as a miss in recall |

Every check has `status`, `confidence`, `reason`, a `scope` or `assessment_scope`,
both values and both sides' evidence. `confidence` is `high` or `low` for MISMATCH
and MISSING, and null otherwise. **Low** marks patterns that a common,
meaning-preserving translation choice can also produce:

| Alarm | Low confidence when |
|---|---|
| Entity MISSING | Every missing item is abstract (-ment, -tion, ...), outside subject/object roles, or possibly abbreviated by a fingerspelled letter string. In 2.0: the gloss has pointing/classifier/pronoun mentions or unresolved content |
| Action MISSING | No missing predicate is a main verb, or the English has several sentences |
| Negation MISSING | The English negation is not on a main predicate |
| Negation MISMATCH | A head-shake without a sign, or an added sign in multi-sentence English |
| Roles MISMATCH | Based on gloss word order (except English-order ASLG-PC12 notation) |
| 2.0 unmatched event MISSING | The gloss has classifier events or unresolved content |

The rule comparator returns one check per fact type (`entities`, `action`,
`negation`, `numbers`, `roles`). The event comparator returns a list of per-event
checks (`predicate`, `scope`, `entities`, `roles`, `negation`, `numbers`) plus
`alignment` and `extraction` rows, each naming its English and gloss event.

## 1.0 fact card

Kept for the default checker. Five fields, each with `state` (KNOWN or UNKNOWN),
`value`, `reason`, `evidence` and optional `scope`:

| Fact | KNOWN value | 2.0 equivalent |
|---|---|---|
| entities | list of labels (`NAME:ALICE`, `APPLE`) | mention labels |
| action | one predicate label | the event predicate when there is exactly one event |
| negation | `{"action", "negative"}` | event polarity |
| numbers | `[{"entity", "count"}]` | event quantities |
| roles | `{"action", "agent", "patient"}` | event roles |

The natural readers also attach an **analysis block** that the rule comparator uses.
English: `content.entities` (label, candidates, dep, name, core, abstract, given),
`content.predicates` (label, candidates, light, dictionary, main, dep, negated),
`content.sentences`, `content.negative_sentence`, `content.negation_on_main_predicate`,
`content.negation_evidence`, `content.roles`. Gloss: `signs` (index, kind, core,
concepts, name, name_sign), `numerals`, `number_attachments`, `unattached_numbers`,
`manual_negation`, `negative_meaning_signs`, `spellings`, `pointing`, `classifier`,
`clauses`, `roles_gate`, `nmm`, `notation`, `unrecognized`, `ambiguous_labels`.
These fields are reader internals; new consumers should read the 2.0 graph.

## Producing and comparing

```sh
python -m signir ir --english "..." --gloss "..." --gloss-nmm negation=false   # print 2.0 graphs (CPU)
python -m signir check --english "..." --gloss "..."                           # default rule checker
python -m signir event-check --engine rules --english "..." --gloss "..." --out private/events/run-01
python -m signir event-check --engine model --config configs/events-ollama.json --english "..." --gloss "..." --out ...
python scripts/export_schema.py                                                # refresh the JSON Schema
```
