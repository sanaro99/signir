# One-attempt correction protocol

The baseline checker must be evaluated and frozen before starting the correction
experiment. This release demonstrates the workflow using authored saved
responses after its controlled evaluation. No paid service or live translator
is invoked. Existing earlier-project output is sufficient for feasibility, but
does not prove its original generation environment is runnable today.

`CorrectionAdapter` is a callable taking a JSON-compatible dictionary:

```json
{"id":"pair-id","english":"original English","original_gloss":"original gloss","diagnostic":{"numbers":{"status":"MISMATCH"}},"instruction":"One correction attempt for the explicit diagnostics; retain other facts."}
```

Actual diagnostics include all checks, values and evidence. The adapter returns
one gloss string. It receives no reference translation or gold label. The
`correct_once(pair, adapter, method_id)` function calls it exactly once, with no
retry, recursive repair or selection among candidates. Adapter exceptions fail
the attempt; callers must not silently retry under the same experimental ID.

The CLI's `SavedResponses` adapter accepts only an exact ID, English and original
gloss match. This makes fixture misuse visible. A production adapter can implement
the same callable contract; fix its model snapshot, prompt, settings, seed and
budget before collecting results, and record them with the method ID. Adapter
authors are responsible for ensuring a single underlying generation call.

The output preserves original and corrected glosses, both complete checker
results, request diagnostics, method and exactly one attempt. Improvements mean
MISMATCH to MATCH. Regressions include MATCH to MISMATCH/UNKNOWN or UNKNOWN to
MISMATCH. Loss of coverage is recorded separately, including MISMATCH to UNKNOWN;
abstention is never counted as a successful correction. Gained coverage is also
recorded without automatically calling it better translation.

The two shipped fixtures include a number repair and a number repair which
changes a person incorrectly. The second therefore records both an apparent
improvement and a regression. These outputs are intentionally authored for
software testing. A better checker result alone is not proof of better ASL;
qualified review and independent judgments are required for that conclusion.
