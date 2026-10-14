# SignIR 1.0

One record per side. Top-level keys: `version` (`"1.0"`), `language` (`english`
or `gloss`), unchanged `text`, whitespace `tokens`, versioned `extractor` ID and
`facts`. Five fact keys are always present:

| Fact | KNOWN value |
| --- | --- |
| entities | List of canonical names (`NAME:ALICE`) or supported noun labels (`APPLE`); duplicates retained |
| action | One canonical action string, e.g. `BUY` |
| negation | `{"action":"BUY","negative":true}` |
| numbers | `[{"entity":"APPLE","count":3}]` |
| roles | `{"action":"HELP","agent":"NAME:ALICE","patient":"NAME:BOB"}` |

Every fact has `state` (KNOWN or UNKNOWN), `value` (null for UNKNOWN), `reason`,
and an `evidence` array. Each evidence span has integer `start`, `end` and exact
`text`. Offsets are **zero-based, half-open Unicode character positions**, not
byte offsets or token indices. `original[start:end]` must equal span text.
UNKNOWN may include observed spans explaining why a fragment is unsupported.
KNOWN means an explicit supported observation, not a guarantee of extractor
accuracy or corpus-wide semantic completeness.

`schema.validate` rejects unsupported versions, missing checks, invalid states,
malformed values and invalid evidence. Values and evidence are JSON serializable.
`compare` accepts two SignIR records directly, independently of extraction.

Comparison rules, in order:

1. Any UNKNOWN side yields UNKNOWN.
2. Negation and roles require the same action; otherwise UNKNOWN.
3. Unequal entity/count inventory sizes yield UNKNOWN, because omission or
   repeated mention cannot establish a complete alignment.
4. Number facts require the same entity multiset; otherwise UNKNOWN.
5. Equal canonical values yield MATCH; explicit conflicts yield MISMATCH.
   Lists are compared as multisets without dropping repetitions.

This is a whole-check summary, not a truth-entailment engine. When partial facts
cannot align, the summary abstains even if some observations match. No count,
polarity or role is detached from its entity/action to improve an overlap score.

## Supported English grammar

`Name [does|did not] Verb Object [and Object]* [.]`, with exact single spaces.
Each Object is `[count] NameOrNoun`. Names use capitalized ASCII words or
hyphenated capitalized words; common pronouns are excluded. Nouns: apple, book,
dog, cat, teacher, student and their plural forms. Verbs: buy, sell, help, see,
visit, like, with the listed present/past forms in `english.py`. Counts: ASCII
nonnegative decimal integers up to 18 digits, or zero through ten. Articles,
passives and multiple clauses are unsupported. Coordination preserves counts
but role summaries abstain when there is more than one object.

## Supported gloss fragment and fixture annotation v1

Labels are case sensitive. Actions: BUY, SELL, HELP, SEE, VISIT, LIKE. Nouns:
APPLE, BOOK, DOG, CAT, TEACHER, STUDENT. Names: `fs-ALICE` or `fs-A-L-I-C-E`;
single-letter sequences join, while multi-letter hyphenated names stay hyphenated.
Counts immediately precede their entity label. Unknown/directional/classifier
labels are preserved, but the whole fragment abstains. There must be exactly one
supported action occurrence. Nothing is inferred from overall gloss word order.

Synthetic metadata labels `AGENT:fs-ALICE`, `PATIENT:APPLE`, `NEG:BUY`, `POS:BUY`
explicitly encode facts for software tests. They are **not a standard ASL gloss
convention or a natural-language translation**. A plain `3 APPLE` following an
explicit `PATIENT:APPLE` is one attached count, not another participant.
Repeated unannotated nouns remain repeated observations.

NOT is scoped only when the entire fragment contains one supported action and
no unknown labels. Missing, conflicting, or wrong-action polarity markers are
UNKNOWN. Real signing can carry negation non-manually; its absence from written
gloss cannot prove positive polarity. IX, spatial loci, inflection and natural
non-manual tiers need an independently validated annotation adapter.

## Natural reader extensions (package 0.2)

The value shapes remain SignIR 1.0. Optional fact scope identifies lexical mentions, one lexical predicate, one explicitly negated predicate or explicit number attachments. Counts may represent quantities, currency units or documented numeric identifiers (CHAPTER, PART, PAGE, SECTION, VOLUME); the internal integer key remains count. They never become a count of a different thing, e.g. $100 is DOLLAR=100 rather than CARD=100. AGE 15 does not imply an explicit YEAR unit.

Optional observations retain lexical candidates independently of whole-field assessability. Gloss unrecognized, ambiguous_labels and unattached_numbers retain original evidence. English model metadata and unrecognized_predicates expose uncertainty. Natural entity inventories are lexical observations, not complete entity semantics; a different inventory returns UNKNOWN. A scoped MATCH is not whole-sentence equivalence.
