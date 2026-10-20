# Event engine validation — 2026-10-20

Publication branch: `feat/event-ir-pr`, based on the current `main`. The only
existing Python module changed is CLI command registration and dispatch. The
new implementation, including its input-validation helpers, lives under
`signir/events/`. Earlier local semantic repairs and research reports are
excluded from this PR.

## Executed checks

| Check | Result |
|---|---|
| Complete publication suite, including existing Spark tests | 114 tests passed |
| Event-only suite | 29 tests passed |
| Authored saved-graph demo | 4 rows processed, no extraction/report errors |
| Paired audit of saved demo runs | IDs/text matched; coverage transitions reported |
| Editable event-extra installation | Passed |
| Wheel build and package inspection | Passed; engine and event fixtures included |
| CLI help and legacy fixture demo without optional dependencies | Passed |
| Event command without event dependencies | Actionable setup error, exit 2 |
| Existing tracked diff whitespace check | Passed |
| Fresh implementation review and targeted re-review | Findings fixed; no remaining substantive findings reported |

Test environment: Python 3.11.2, Linux x86-64, Pydantic 2.14.1, SciPy 1.17.1,
NumPy 2.4.6. The original natural tests used the repository's spaCy/LemmInflect
versions and en_core_web_sm 3.8.0. New event tests do not use that reader.

## What the tests establish

Schema tests reject incorrect original-source slices, dangling and duplicate
IDs, cyclic event parents, unsupported versions, non-finite quantities,
incoherent ranges, excessive graphs and prohibited gloss evidence conventions.
Numeric comparison tests distinguish equality, disjointness and overlap.

Comparator tests cover reordered events, swapped quantities, indistinguishable
repeated events, partial graphs, repeated participant labels, explicit complete
role reversal, incomplete role memberships, uncertain lexical meanings and
nonasserted scope. Empty extraction is not a vacuous MATCH.

Actual loopback HTTP servers exercise Ollama and vLLM request formats, source
independence, evidence offset conversion, response/context limits, redirects,
refusals, truncation, model-name mismatch, invalid JSON, duplicate JSON keys,
invalid graphs, deeply nested JSON and malformed chunked responses. A failed
HTTP row does not prevent subsequent rows from being reported.

Workflow tests cover input/output protection, duplicate IDs, saved graph
comparison, incompatible side labels, paired IDs/text, error denominators,
human-label metadata and mismatch recall that includes abstentions/errors.
Reviewed lexical alternatives cannot be silently discarded when their exact
label and kind occur in extracted evidence.

## Review fixes

The fresh review identified two reproduced defects:

1. Partial same-role participant lists could produce a false conflict. Role
   completeness is now explicit and false by default; different partial
   inventories abstain. A completeness declaration remains a model proposal.
2. Malformed HTTP framing and deeply nested JSON could escape the extraction
   error boundary and terminate a batch. Both now produce recorded failures;
   later rows continue.

Regression tests were observed failing before the fixes and passing afterward.
The reviewer rechecked the fixes and the new lexical-alternative validation.

## What remains unmeasured

The PR preserves the Spark experiment, instructions, package data and tests
already on `main`. A fresh review confirmed that event imports resolve within
the isolated publication checkout and need none of the earlier local repairs.

The user explicitly deferred live inference to a separate DGX Spark workspace.
No Ollama/vLLM model, Spark GPU, quantized checkpoint, natural corpus extraction,
latency, memory benchmark or independent human accuracy evaluation ran here.
The example configurations are serving templates, not validated deployments.

This implementation does not establish a reduction in natural UNKNOWN cases.
The legacy measurements in the repository README remain separate from the
event engine. The authored demo's assessments are software behavior, not natural
ASL accuracy. The next empirical step is
the configured local model run, followed by independent annotation and an
untouched document-held-out evaluation described in [the guide](event-checker.md).
