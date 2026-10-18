#!/usr/bin/env bash
# Software workflow check only. Executes no model and makes no CUDA claim.
set -euo pipefail
if [[ $# != 1 ]]; then
  printf 'Usage: bash experiments/dgx-spark/replay-smoke.sh NEW_OUTPUT_DIRECTORY\n' >&2
  exit 2
fi
SIGNIR_SMOKE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SIGNIR_SMOKE_OUTPUT=$(realpath -m -- "$1")
SIGNIR_PYTHON=${SIGNIR_PYTHON:-python3}
SIGNIR_FIXTURES="$SIGNIR_SMOKE_ROOT/experiments/dgx-spark/fixtures"
mkdir -p -- "$SIGNIR_SMOKE_OUTPUT"
cd -- "$SIGNIR_SMOKE_ROOT"
"$SIGNIR_PYTHON" -m signir.gpu freeze --input "$SIGNIR_FIXTURES/pairs.jsonl" \
  --revision aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --container-image replay \
  --out "$SIGNIR_SMOKE_OUTPUT/freeze.json"
"$SIGNIR_PYTHON" -m signir.gpu replay --input "$SIGNIR_FIXTURES/pairs.jsonl" \
  --freeze "$SIGNIR_SMOKE_OUTPUT/freeze.json" --responses "$SIGNIR_FIXTURES/responses.jsonl" \
  --out "$SIGNIR_SMOKE_OUTPUT/run"
"$SIGNIR_PYTHON" -m signir.gpu score --records "$SIGNIR_SMOKE_OUTPUT/run/records.jsonl" \
  --gold "$SIGNIR_FIXTURES/gold.jsonl" --out "$SIGNIR_SMOKE_OUTPUT/scored"
"$SIGNIR_PYTHON" -m signir.gpu annotate --input "$SIGNIR_FIXTURES/pairs.jsonl" \
  --out "$SIGNIR_SMOKE_OUTPUT/annotations"
printf 'Replay smoke workflow complete. These are authored responses, not GPU/model results.\n'
