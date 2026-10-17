# SignIR extraction experiment on one DGX Spark

Compare three fixed approaches to the same English/gloss pairs:

1. `cpu`: the existing SignIR readers and deterministic comparison.
2. `structured`: independently extract each side using one frozen local model,
   then compare the records deterministically.
3. `judge`: ask that same model to judge selected facts using both texts.

This package is an inference experiment. It does not train a model, generate
translations or assess ASL grammaticality. There are no measured GPU results in
this repository. The authored replay fixtures test software plumbing only.

## Run on Mike's DGX Spark

Requires Docker with the NVIDIA Container Toolkit, network access for container,
model and baseline dependencies, and disk space for their downloads. Run from a
clean checkout of this feature branch. The launcher targets the Spark's ARM64
architecture and uses NVIDIA's recommended Qwen3.8-27B NVFP4 image recipe.

```bash
git clone --branch feat/dgx-spark-experiments https://github.com/sanaro99/signir.git
cd signir
# Four public, authored diagnostic pairs: test setup before using restricted data.
bash experiments/dgx-spark/run.sh \
  experiments/dgx-spark/fixtures/pairs.jsonl \
  results/dgx-spark-authored-01

# After the smoke run, use an authorized local pilot dataset.
bash experiments/dgx-spark/run.sh \
  private/pilot-pairs.jsonl \
  private/dgx-spark-pilot-01
```

An optional third argument selects a configuration JSON. Default settings are in
`config.json`: batch size 4, 8,192-token context, 3,072 output tokens, seed 42,
temperature 0, thinking disabled, eager execution, one GPU, and 65% GPU memory
utilization. Greedy decoding and a seed do not guarantee bit-identical CUDA
results. Excessively long inputs remain logged failures; they are not truncated
silently. These settings are for short fact records, not the model's full context.

The launcher pulls `vllm/vllm-openai:qwen38`, resolves its immutable digest, and
mounts source/input/config read-only. Override `SIGNIR_IMAGE` with a compatible
image digest to reproduce an earlier run. `SIGNIR_MODEL_CACHE` selects a persistent
host download directory. An existing `HF_TOKEN` environment variable is passed
only if needed for model access; credentials are not saved in manifests.

Before model loading, `python -m signir.gpu preflight` allocates CUDA tensors,
executes matrix multiplication and verifies the result. Missing CUDA is a setup
error. `run` cannot use a replay freeze and has no CPU inference fallback.
vLLM performs inference locally in that CUDA container; no API server port is
opened. No English/gloss text is sent to a hosted model service.

The first launch installs the documented CPU extraction dependencies inside the
ephemeral container, freezes the model/tokenizer's current Hugging Face commit,
and fingerprints settings, source, prompts, input bytes, resource hashes and
package versions. Subsequent model loading uses that commit, not `main`.
Real runs fingerprint the full installed distribution inventory. CPU replay still
verifies the English reader's transitive CPU dependencies and resource hashes,
while allowing CUDA/vLLM dependencies to differ.
The container must support the selected model and JSON structured outputs.
Hardware compatibility still requires an actual Spark smoke run.

## Input and study design

UTF-8 JSONL, one unique pair per line:

```json
{"id":"pilot-001","english":"Alice buys 3 apples.","gloss":"fs-ALICE BUY 9 APPLE","source_group":"authored-document-01","split":"dev"}
```

`source_group` identifies the actual source document. Optional `family_id` groups
controlled variants. Allowed splits are `dev`, `test`, `diagnostic` (default).
Document/family groups and identical normalized English cannot cross splits.
Keep related variants together. A user-supplied group label is not proof that
corpus documents have been correctly identified.

Start with approximately 50–100 independently reviewed pairs sampled across
assessed and UNKNOWN cases, explicit quantities, negation, properties, ambiguous
labels and unsupported multi-event inputs. Keep prompt development separate from
evaluation documents. This runner processes the supplied input exactly: it does
not select an easy subset, create gold labels or invent faithful originals.
Review mutations independently of the old checker's recoverability. The four
bundled pairs and artificial `POS:BUY` metadata are authored software examples.

The extraction call receives only its language and original text. It never sees
the opposite side, gold labels, reference gloss, provenance, direct-judge output,
or the other extraction result. The direct judge receives just the two texts.
All protocols require original evidence spans. Schema validity is not semantic
correctness. Roles in gloss remain UNKNOWN; missing NOT cannot prove positive
polarity. The current schema cannot resolve general multiple-event alignment.
The experiment adds documented conservative guards to the committed comparator
for repeated count entities and differing property interpretations; it does not
include the unrelated uncommitted research repairs from another checkout.

## Outputs, resume and failures

The run directory contains:

- `freeze.json`: immutable experiment definition and hashes.
- `runtime-packages.txt`: installed package versions.
- `run/manifest.json`: CUDA hardware/runtime, backend, completion and failure counts.
- `run/cache/*.json`: frozen requests and raw outputs, finish reasons, token counts
  and amortized batch generation time. Initial model loading is outside that time.
- `run/records.jsonl`: all three approaches, extracted facts, failures and evidence.
- `run/summary.json`: coverage and failed-pair counts, with no invented accuracy.
- `run/checks.csv`: one row per pair/approach/fact with reasons and evidence.

Rerun the same command to resume the same freeze and cache. Use the recorded image
digest if the image tag has moved. Changed code, prompts, inputs, dependencies,
config or runtime identity require a new directory/freeze. Cached failed responses
are retained, not silently retried until a favorable answer appears. Finish reason
`length`, malformed JSON, wrong types, unsupported roles and invalid evidence are
logged failures. Exit 2 means setup/input error; exit 3 means completed processing
with failed model requests. Semantic MISMATCH alone is not a process error.
Cache entries are published atomically, so an interrupted write cannot become a
partial cached response. Model initialization failures abort as setup errors and
are not cached as predictions. Failed/interrupted runs retain explicit manifest
status. The initial runtime package listing is preserved during resume.

## Independent annotation and scoring

The annotation/scoring commands run on CPU with the package available:

```bash
python -m signir.gpu annotate --input private/pilot-pairs.jsonl \
  --out private/pilot-annotations
```

Give `english.jsonl` and `gloss.jsonl` to independent reviewers without the other
side or checker outputs. They edit each record's facts, reasons, evidence and
KNOWN/UNKNOWN states. Freeze these annotations before unblinding. `checks.jsonl`
is for subsequent paired adjudication, not the blind reading stage. Set each
completed row's `annotation_kind` to `human-reviewed`; blank templates retain
`unreviewed` and are rejected as gold. An explicitly UNKNOWN fact means genuinely
unassessable within this representation; omit a check key if it was not labeled.

```bash
python -m signir.gpu assemble --input private/pilot-pairs.jsonl \
  --english private/pilot-annotations/english.jsonl \
  --gloss private/pilot-annotations/gloss.jsonl \
  --checks private/pilot-annotations/checks.jsonl --out private/pilot-gold.jsonl

python -m signir.gpu score \
  --records private/dgx-spark-pilot-01/run/records.jsonl \
  --gold private/pilot-gold.jsonl --out private/dgx-spark-pilot-01/scored
```

Gold JSONL joins by ID and may contain adjudicated `checks` alone or both complete
side records. Reviewed text and IDs must match the input exactly. `authored` gold
is accepted for software fixtures and identified separately in the summary.
Check-only gold must also include `pair_sha256`, computed with
`signir.gpu.storage.digest({"english": original_english, "gloss": original_gloss})`.
This prevents reusing labels for changed text under the same ID. Score summaries
record hashes of the prediction and gold files.
Qualified ASL review is needed for claims about natural gloss interpretation;
LLM/assistant annotations must not be relabeled human-reviewed.

Per-field reports include mismatch precision/recall/F1, confusion tables, accuracy
counting abstentions as incorrect on known labels, assertions on gold UNKNOWN,
and failed-pair counts. Missing labels are excluded from denominators. Errors and
UNKNOWN predictions cannot disappear from recall. Extraction metrics compare
entire canonical field values. Human-contract comparison is a separate control
showing what the comparator can do with independently supplied facts.

## CPU replay smoke check

Install the package in a separate Linux environment; the authored fixture path
does not require CUDA or the natural-model extra:

```bash
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install -e .
bash experiments/dgx-spark/replay-smoke.sh results/replay-smoke-01
python -m unittest discover -s tests -p 'test_gpu_*.py' -v
```

Replay produces `cuda_inference: false` and a `replay` backend manifest. Its fixture
responses are authored, not generated by Qwen. It cannot demonstrate model
accuracy, GPU performance, or natural ASL error detection. The complete existing
suite also needs the natural extra and English model documented in the root README.

Keep restricted inputs, caches, annotation sheets and sentence-level results under
ignored `private/` or `results/`. No dataset transfer or results publication is
performed by these scripts.

## Technical sources checked October 17, 2026

- [NVIDIA's single-Spark model recommendation](https://build.nvidia.com/spark/vllm/choose-recipe)
- [NVIDIA's image/model setup](https://build.nvidia.com/spark/vllm/instructions)
- [vLLM JSON structured outputs, including offline inference](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [Qwen3.8 model and Spark recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B?hardware=dgx_spark_gb10)
