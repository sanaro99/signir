# Recovered Sign F1 implementation

`signir/baselines.py` adapts only the lexical-core reduction and per-sentence
multiset F1 from the earlier project's
`src/aslgloss/evaluation/sign_selection.py`. The actual local source SHA-256 is
recorded in `docs/baseline-parity.json`. The old implementation was executed
directly via its pure functions and compared on 643 saved pairs and four edge
cases: 647 comparisons, zero differences. Heavy retrieval and metric imports
were excluded; no claim is made that the entire old environment was installed.

The earlier metric removes handshape prefixes, fingerspelling/naming prefixes,
loci, variants, compounds and nonletters, retaining a heuristic lexical core.
Digits can disappear entirely. These are deliberate compatibility limitations,
not SignIR normalization rules. Case-sensitive raw whitespace multiset F1 is the
separate simple word-matching baseline. Both compare candidate to reference
gloss, not English to gloss. This is an explicit extra-reference requirement.

Original licence notice:

MIT License

Copyright (c) 2026 The asl-gloss-stage1 Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Natural extraction dependencies (0.2)

No dependency source/model is vendored. The optional natural extra installs:

- spaCy 3.8.16: MIT; [official documentation](https://spacy.io/usage).
- en_core_web_sm 3.8.0: MIT according to the installed model metadata; [model documentation](https://spacy.io/models/en). The 12.8 MB package was downloaded and executed locally on English only.
- LemmInflect 0.2.3: MIT; [source and documentation](https://github.com/bjascob/LemmInflect). Its dictionary is derived from the NIH SPECIALIST Lexicon. It is used for independent lexical lookups, not a claim of ASL grammar.

Package versions and SHA-256 fingerprints of model/dictionary resources are included in new manifests and freezes. Model redistribution should retain the dependency's own licence and attribution. SignON and AMR remain background ideas only.
