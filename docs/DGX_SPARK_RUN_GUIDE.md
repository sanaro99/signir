# Run the SignIR experiment on DGX Spark

Start here when setting up the experiment on the Spark. This page covers the
complete visit: obtain the code, check the machine, run a small CUDA test, run the
diagnostic challenge, and collect the results.

## What this experiment answers

Does a local model recover useful English/gloss facts beyond the current checker,
and does that improve error detection without adding false alarms?

Every input pair goes through three approaches:

| Approach | What runs |
|---|---|
| CPU baseline | Existing English/gloss readers and fixed comparison rules |
| Independent extraction | CUDA model reads English and gloss separately; fixed rules compare the facts |
| Direct judgment | The same CUDA model sees both texts and judges selected facts |

The model is `nvidia/Qwen3.8-27B-NVFP4`, loaded through the repository's vLLM Docker
launcher. Ollama is used by the separate generation experiment. Run the two
experiments in separate sessions so they do not compete for Spark memory.

## Confirmed 128 GB run profile

The target machine has **128 GB of unified system memory**, shared by CPU, GPU
and the operating system. Installed capacity does not mean all 128 GB is free.

| Setting | Initial value |
|---|---|
| Model | `nvidia/Qwen3.8-27B-NVFP4` |
| First CUDA smoke | `config-serial.json`, one active request |
| Authored challenge and natural pilot | `config.json`, batch size 4 |
| Context / output reserve | 8,192 / 3,072 tokens |
| vLLM executor budget | `gpu_memory_utilization: 0.65` |
| Other model servers | Unload their models before this experiment |

The memory fraction is a vLLM executor setting, not a guarantee about total host
memory use. Keep the existing conservative settings for the first measured run;
test batch size 8 only later in a separate calibration directory. Record actual
available memory, load time and device snapshots rather than inferring fit from
installed capacity. [NVIDIA lists the quantized 27B model for one Spark](https://build.nvidia.com/spark/vllm/choose-recipe).

Before this CUDA session, use the same Ollama service as the generation
experiment to release any still-loaded models:

```bash
ollama ps
# If listed as loaded, stop the generation and smoke models before continuing.
ollama stop qwen3.8:27b
ollama stop qwen3:0.6b
ollama stop all-minilm:latest
```

If Ollama is not installed or running, this handoff step is unnecessary. Run the
serial smoke below, then the 52-pair challenge and an independently reviewed
natural pilot. The generation experiment follows after this container exits.

## 1. Before the visit

The machine owner can confirm:

- Linux/ARM64, NVIDIA GPU visibility, and available system memory.
- Docker and NVIDIA Container Toolkit configured for `docker run --gpus all`.
- Internet access and free disk space for the container, model weights and outputs.

The research team brings the code and, for the later natural-data pilot, an
authorized local English/gloss file. The first two runs below use public authored
fixtures and require no research corpus. Drivers, container setup and Python
packages do not need to be installed in the generation repository's environment.

On the Spark, record:

```bash
uname -m
nvidia-smi
free -h
df -h "$HOME"
docker --version
docker info
python3 --version
```

The launcher requires `aarch64`/`arm64`, Python 3.11 or newer, and a working Docker
daemon available to the current user. Docker GPU access is verified by the CUDA
operation inside the first run. If container support needs installation, use the
[NVIDIA Container Toolkit guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
and [Spark vLLM setup](https://build.nvidia.com/spark/vllm/instructions).

## 2. Get the code

Use a fresh checkout of the published program:

```bash
git clone https://github.com/sanaro99/signir.git "$HOME/signir-spark"
cd "$HOME/signir-spark"
```

Confirm that the entry points are present:

```bash
test -f experiments/dgx-spark/run.sh
test -f experiments/dgx-spark/run-challenge.sh
python3 -m signir.gpu --help
```

The launcher installs baseline dependencies inside its CUDA container. No host
PyTorch/vLLM installation or host virtual environment is required for these steps.

## 3. First run: four authored pairs on CUDA

Run from the repository root:

```bash
cd "$HOME/signir-spark"
bash experiments/dgx-spark/run.sh \
  experiments/dgx-spark/fixtures/pairs.jsonl \
  results/spark-smoke-128gb-01 experiments/dgx-spark/config-serial.json
```

The first launch downloads the ARM64 image and model, executes an actual CUDA
tensor check, installs the CPU baseline dependencies, freezes the experiment,
and runs all three approaches. It exposes no inference server port.

Inspect:

```bash
cat results/spark-smoke-128gb-01/run/report.md
cat results/spark-smoke-128gb-01/run/manifest.json
```

A completed processing run has `status: complete` or `complete_with_errors`.
Confirm `cuda_inference: true`, the expected GPU/runtime in `backend.hardware`,
and inspect `failed_requests`. Exit 3 means model requests failed validation or
generation; their raw responses and reports are retained. It does not mean that
a semantic mismatch is a software failure. Exit 2 means setup/input failure.
Resolve setup or response-contract failures before moving to the challenge.

## 4. Run and score the 52-pair challenge

```bash
cd "$HOME/signir-spark"
bash experiments/dgx-spark/run-challenge.sh results/spark-challenge-01
```

This command creates 52 distinct authored pairs across 16 phenomena, runs actual
CUDA inference, and scores the partial authored expectations. Successful scoring
publishes `scored/complete.json` with prediction/gold/report fingerprints.

| Open this file | What it tells us |
|---|---|
| `results/spark-challenge-01/scored/report.md` | Readable coverage, failures and candidate findings |
| `results/spark-challenge-01/scored/summary.json` | Per-field and per-phenomenon metrics against authored labels |
| `results/spark-challenge-01/scored/analysis.json` | CPU/model hybrids, alarm accountability and coverage changes |
| `results/spark-challenge-01/scored/review_queue.jsonl` | Ranked cases for manual inspection, with source and evidence |
| `results/spark-challenge-01/inference/run/manifest.json` | Model load, CPU baseline, CUDA batch timings and resource snapshots |
| `results/spark-challenge-01/inference/run/records.jsonl` | All predictions, extracted facts and failures |

These labels test literal authored cases. Natural-ASL accuracy and grammaticality
require independently reviewed natural data. Review-queue entries are candidates,
and UNKNOWN remains an explicit outcome. Gold-side controls are unmeasured when
independent side annotations are absent.

## 5. Natural-data pilot, after the challenge

Place 50–100 authorized local pairs in `private/pilot-pairs.jsonl`, one JSON object
per line. Keep document/family variants in the same split. Example format only:

```json
{"id":"pilot-001","english":"Alice buys 3 apples.","gloss":"fs-ALICE BUY 9 APPLE","source_group":"document-01","split":"diagnostic"}
```

```bash
cd "$HOME/signir-spark"
bash experiments/dgx-spark/run.sh \
  private/pilot-pairs.jsonl private/spark-pilot-01
python3 -m signir.gpu annotate \
  --input private/pilot-pairs.jsonl --out private/pilot-annotations
```

The initial report measures coverage/disagreements. Give the independent reading
sheets to reviewers before showing predictions. Follow the
[annotation and scoring procedure](../experiments/dgx-spark/README.md#independent-annotation-and-scoring)
to assemble reviewed gold and measure correctness. Restricted texts, annotations,
caches and sentence-level outputs remain in `private/` or `results/`.

## 6. Resume, calibration and handoff

Rerun the same launcher command to resume unchanged inputs/settings. If the image
tag has moved, use the digest recorded in `freeze.json` as `SIGNIR_IMAGE`:

```bash
export SIGNIR_IMAGE="$(python3 -c 'import json; print(json.load(open("results/spark-challenge-01/inference/freeze.json"))["container_image"])')"
bash experiments/dgx-spark/run-challenge.sh results/spark-challenge-01
```

Use fresh output directories when changing code, input, model or config. A partial
or modified published `challenge/` or `scored/` directory stops before GPU setup;
preserve it and use a new suite directory. Cached failed model responses remain
part of the original attempt.

For speed calibration, use a small fixed input and fresh directories with
`config-serial.json`, `config.json`, and optionally `config-throughput.json`.
The throughput profile changes both batch size and prefix caching. Compare timing,
failures and semantic outputs before selecting a profile for the main study; a
warm-cache resume does not measure fresh inference. See the
[review/run plan](../experiments/dgx-spark/REVIEW.md).

Return the complete output directory and the Git revision (`git rev-parse HEAD`)
to the team through the agreed research storage. Keep the raw cache, freeze and
manifest alongside the reports. After the Docker run exits, its container stops;
downloaded models remain under `$HOME/.cache/signir-huggingface` for reuse.

## If a step fails

| Symptom | Next action |
|---|---|
| Docker unavailable or permission denied | Resolve Docker access with the machine owner before rerunning |
| No CUDA or GPU kernel/model initialization failure | Check the Spark driver/container recipe; the run cannot fall back to CPU |
| Out of memory | Release other GPU models; inspect actual usage; use a fresh smaller-batch config if needed |
| Context overflow | Inspect the recorded failing request; increase an explicitly frozen context budget in a fresh run |
| Output already belongs to another freeze | Choose a new output directory |
| Authored scores look good but natural data is mostly UNKNOWN | Inspect reader/comparator controls and obtain independent annotations |

Software and tokenizer checks have run locally. CUDA performance, Spark memory
headroom and natural-data model accuracy still require execution on the device.
Detailed implementation and validation are in the
[experiment README](../experiments/dgx-spark/README.md) and
[validation report](dgx-spark-validation.md).
