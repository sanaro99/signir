#!/usr/bin/env bash
# Run on one DGX Spark. The experiment never exposes a network inference port.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  printf 'Usage: bash experiments/dgx-spark/run.sh INPUT.jsonl RUN_DIRECTORY [CONFIG.json]\n' >&2
  exit 2
fi
SIGNIR_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SIGNIR_INPUT=$(realpath -- "$1")
SIGNIR_OUTPUT=$(realpath -m -- "$2")
SIGNIR_CONFIG=$(realpath -- "${3:-$SIGNIR_REPO/experiments/dgx-spark/config.json}")
SIGNIR_IMAGE=${SIGNIR_IMAGE:-vllm/vllm-openai:qwen38}
SIGNIR_MODEL_CACHE=${SIGNIR_MODEL_CACHE:-$HOME/.cache/signir-huggingface}
export SIGNIR_REPO SIGNIR_INPUT SIGNIR_OUTPUT SIGNIR_CONFIG
python3 - <<'PY'
import os
from pathlib import Path
out = Path(os.environ['SIGNIR_OUTPUT'])
for key in ('SIGNIR_INPUT', 'SIGNIR_CONFIG'):
    source = Path(os.environ[key])
    if not source.is_file() or source == out or out in source.parents:
        raise SystemExit('Output cannot replace/contain input or configuration')
repo = Path(os.environ['SIGNIR_REPO'])
if out == repo or out in repo.parents:
    raise SystemExit('Output cannot replace/contain the source repository')
PY
case "$(uname -m)" in
  aarch64|arm64) ;;
  *) printf 'This launcher targets an ARM64 DGX Spark. Use replay for CPU validation.\n' >&2; exit 2 ;;
esac
docker info >/dev/null
docker pull "$SIGNIR_IMAGE"
SIGNIR_DIGEST=$(docker image inspect --format '{{index .RepoDigests 0}}' "$SIGNIR_IMAGE")
SIGNIR_ARCH=$(docker image inspect --format '{{.Architecture}}' "$SIGNIR_DIGEST")
if [[ "$SIGNIR_ARCH" != arm64 || "$SIGNIR_DIGEST" != *@sha256:* ]]; then
  printf 'Expected an immutable ARM64 image digest.\n' >&2
  exit 2
fi
mkdir -p -- "$SIGNIR_OUTPUT" "$SIGNIR_MODEL_CACHE"
docker run --rm --gpus all --ipc=host --shm-size=8g \
  --mount "type=bind,src=$SIGNIR_REPO,dst=/workspace,readonly" \
  --mount "type=bind,src=$SIGNIR_INPUT,dst=/input/pairs.jsonl,readonly" \
  --mount "type=bind,src=$SIGNIR_CONFIG,dst=/settings/config.json,readonly" \
  --mount "type=bind,src=$SIGNIR_OUTPUT,dst=/results" \
  --mount "type=bind,src=$SIGNIR_MODEL_CACHE,dst=/model-cache" \
  --env PYTHONPATH=/workspace --env PYTHONDONTWRITEBYTECODE=1 \
  --env "SIGNIR_CONTAINER_IMAGE=$SIGNIR_DIGEST" --env HF_TOKEN \
  --env HF_HOME=/model-cache --env VLLM_TARGET_DEVICE=cuda \
  --workdir /workspace --entrypoint bash "$SIGNIR_DIGEST" \
  /workspace/experiments/dgx-spark/container.sh
