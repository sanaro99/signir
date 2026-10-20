# Event-based SignIR: approved implementation design

The goal is to assess independently supported facts in multi-event English/gloss
pairs while retaining evidence and uncertainty. This implements the local hybrid
architecture selected in chat on 2026-10-19. It is a new, explicit experimental
engine; the legacy checker remains a baseline until an independently annotated
evaluation demonstrates that the new engine should replace it.

## Boundaries

English and gloss are extracted independently. A reader receives one unchanged
input, its indexed tokens, and only notation/lexicon information relevant to that
input. It never receives the other side, a reference translation, or a comparison
result. Local Ollama and vLLM-compatible HTTP servers are supported. No model is
downloaded or server launched automatically.

The model selects token spans. Code converts these to original character offsets
and exact text, then validates the resulting graph with Pydantic. Model errors,
transport errors, and unsupported linguistic evidence are different outcomes.
Schema validity and correct offsets do not establish semantic accuracy.

## Representation

SignIR 2.0 has mentions, multiple events, and unresolved observations. Mentions
retain identity, canonical label, alternatives, kind, and evidence. Events retain
predicate identity and evidence, participant mention IDs, independently supported
roles, polarity, scope, parent-event links, and attached quantities. Quantities
retain their mention, unit, kind, exact decimal value, and comparison operator
(exact, lower/upper bound, interval, approximate). Unknown polarity and scope are
explicit values. Unsupported or inferred roles must remain unresolved.

Validation rejects dangling/duplicate IDs, cycles, unsupported schema versions,
invalid spans, incoherent bounds, non-finite numbers, and contradictory evidence
conventions. Gloss positive polarity requires explicit annotation; absent NOT is
insufficient. No semantic role is established by bare gloss order.

## Gloss resources

A separately configured, versioned JSON lexicon maps exact gloss labels to
reviewed concept candidates with provenance. Multiple candidates are retained.
Only relevant entries are sent to the gloss reader. No restricted lexicon is
bundled. A tiny authored resource can demonstrate the interface but cannot be
described as corpus coverage or ASL validation.

## Alignment and comparison

Candidate scores use lexical predicates and participant labels. Counts, polarity,
role direction, and token order are excluded. SciPy assignment includes unmatched
alternatives. Removing a chosen edge and solving again tests global ambiguity;
insufficiently distinguished edges remain UNKNOWN. Unsupported split/merge event
alignments remain unresolved.

Each aligned event produces predicate, entities, roles, negation, numbers, and
scope checks with values, evidence, reason codes, and assessment scope. Quantity
attachments align within an event; repeated indistinguishable mentions abstain.
Equal exact values or equal supported bounds match; disjoint constraints conflict;
overlapping but non-equivalent constraints remain unknown. Approximation abstains.
Operator scope and parent-event alignment gate event-level comparisons. In the
initial implementation only asserted, unparented events pass the relational
gate; nonasserted contexts require richer operator identity before comparison.
Different partial role lists abstain; conflicts require both role inventories
to explicitly declare completeness, which remains a model proposal.
Unmatched events remain visible; they do not imply an omitted translation.
An unresolved event does not erase supported checks on other events.

## Operational workflow

Separate `event-check`, `event-check-file`, `event-compare`, and `event-audit`
commands expose extraction, saved-record comparison, batch reports, and paired
evaluation. Explicit JSON configuration sets backend, endpoint, model, timeout,
output/context limits, optional revision and lexicon. Local endpoints are the
default. Redirects are rejected. Responses are bounded, refusals/truncation and
model identity mismatches fail visibly. No retry, silent fallback, or repair of
model content. Manifests record exact requests/responses in private reports,
code/prompt/schema/config/lexicon hashes, model identity, runtime versions and
timings. Batch failures stay in denominators and are distinct from UNKNOWN.

Reports compare paired IDs/text, include error/coverage counts, and optionally
score independent human check labels. No labels means coverage only. Existing
643-pair outputs are development material, not independent validation. Qualified
gloss annotation and an untouched document-held-out sample remain necessary.

## Validation and rollout

Regression cases cover swapped counts between repeated BUY events; role reversal;
partial observations; ambiguous alignment; scoped negation and conditions;
numeric bounds; source-independent requests; malformed/truncated model output;
input/output aliases; duplicate IDs; and errors in evaluation denominators.
Run all existing tests in a new Linux environment. Exercise both HTTP protocols
with actual loopback test servers and run authored saved-graph demonstrations.
Run live extraction only if an authorized reachable model endpoint is available.
Do not claim improved natural accuracy or Spark execution from synthetic tests.
