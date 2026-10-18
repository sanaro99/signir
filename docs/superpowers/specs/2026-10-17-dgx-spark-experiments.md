# DGX Spark extraction experiment

The approved experiment compares the existing CPU checker, independent model
extraction followed by deterministic comparison, and direct judgment by the same
frozen model. It tests selected fact preservation, not ASL grammaticality. No
training, translation generation, or automatic repair is included.

Use NVIDIA's single-Spark Qwen3.8-27B NVFP4 vLLM recipe. Actual inference must
execute a CUDA tensor operation before loading the model; CPU fallback is an
error. The Docker launcher uses --gpus all and pins the downloaded image digest.
Freeze the Hugging Face model/tokenizer commit, input bytes, settings, prompts,
schemas, source files, and extraction dependency fingerprints before inference.

Each side's extraction request contains only its language and original text.
Direct judgment receives both texts. Neither protocol receives labels, reference
gloss, provenance, other protocol outputs, or annotations. Require JSON schema
outputs and validate their nested types, exact evidence spans, and UNKNOWN
semantics. Natural gloss roles and absent positive polarity stay UNKNOWN. Retain
the current single-predicate schema and conservative alignment rules.

Cache every request and raw response under its frozen request hash. Resume only
the identical frozen experiment. Preserve malformed/truncated responses and
failed requests as failures; never fabricate a valid model result. A separately
named replay mode supports CPU workflow testing without claiming CUDA inference.

Provide blind English-only/gloss-only annotation packs and optional reviewed gold
records. Without gold, report coverage and failures only. With gold, report
per-field detection, abstentions, unsupported assertions, extraction agreement,
and comparison from gold contracts. UNKNOWN predictions count as missed known
errors. Missing labels are not negative labels. Original candidates are not
assumed faithful. Groups and identical English inputs cannot cross dev/test.

Only authored smoke examples and their literal expected labels ship publicly.
Input text, caches, blind sheets, annotations, and sentence-level reports belong
under ignored private/ or results/. Never publish the unrelated working changes.

Deliver a documented CLI, DGX Docker launcher, example configuration, frozen
prompts, authored replay fixture, tests, and a GitHub feature branch/pull request.
Local validation covers software behavior; actual model/CUDA results require a
DGX Spark run and must not be invented.
