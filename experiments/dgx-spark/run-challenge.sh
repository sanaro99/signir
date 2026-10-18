#!/usr/bin/env bash
# On DGX Spark: build authored probes, run actual CUDA inference, score all results.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 ]]; then
  printf 'Usage: bash experiments/dgx-spark/run-challenge.sh OUTPUT_DIRECTORY [CONFIG.json]\n' >&2
  exit 2
fi
SIGNIR_SUITE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SIGNIR_SUITE_PYTHON=${SIGNIR_PYTHON:-python3}
export PYTHONPATH="$SIGNIR_SUITE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$SIGNIR_SUITE_PYTHON" -m signir.gpu.suite "$@"
