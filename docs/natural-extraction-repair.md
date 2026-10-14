# Natural extraction repair (2026-10-10)

The original readers accepted only a fixture grammar. All 643 natural pairs had zero assessed checks; passing the authored fixtures was insufficient acceptance evidence.

Repair the existing extraction path. Keep both sides independent. Use spaCy en_core_web_sm only on English; use a dictionary-based lexical reader on gloss, retaining original annotation strings and offsets. Extract observable facts separately so unsupported tokens cannot erase unrelated evidence. Keep uncertain event scope, missing polarity and spatial roles unknown.

Add independent observations and scoped comparisons, not guesses of full equivalence. Entity/action inventories are lexical observations; count attachments and explicit action-linked negation remain relational facts. Default results expose scope and warnings. Preserve the existing restricted fixture path where valid. No translator invocation.

Test the entire fixed 643-pair natural run descriptively, saving before/after evidence privately. This is repair/diagnosis data, not held-out accuracy. Inspect a predetermined sample and inject clearly logged count/negation changes into copies of natural pairs. Retain all failures and abstentions. Archive a new versioned controlled freeze because the extraction implementation changed.
