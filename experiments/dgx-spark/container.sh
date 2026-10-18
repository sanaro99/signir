#!/usr/bin/env bash
# Invoked by run.sh inside the pinned CUDA/vLLM container.
set -euo pipefail
python3 -m signir.gpu preflight
# Keep the container-provided CUDA, PyTorch and vLLM builds. Add CPU baseline tools.
SIGNIR_CONSTRAINT_ARGS=()
if [[ -f /results/cpu-constraints.txt ]]; then
  SIGNIR_CONSTRAINT_ARGS=(--constraint /results/cpu-constraints.txt)
fi
python3 -m pip install "${SIGNIR_CONSTRAINT_ARGS[@]}" 'spacy==3.8.16' 'lemminflect==0.2.3' \
  'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'
python3 -m pip check
if [[ ! -e /results/freeze.json ]]; then
  python3 -m signir.gpu freeze --input /input/pairs.jsonl \
    --config /settings/config.json --container-image "$SIGNIR_CONTAINER_IMAGE" \
    --out /results/freeze.json
else
  python3 - <<'PY'
import os
from signir.gpu.storage import read_json, verify_freeze
frozen = read_json('/results/freeze.json')
if frozen['config'] != read_json('/settings/config.json'):
    raise SystemExit('Requested configuration changed; use a fresh run directory')
if frozen['container_image'] != os.environ['SIGNIR_CONTAINER_IMAGE']:
    raise SystemExit('Container image changed; set SIGNIR_IMAGE to the previous digest or use a fresh directory')
verify_freeze('/input/pairs.jsonl', frozen)
PY
fi
python3 - <<'PY'
from pathlib import Path
from signir.gpu.storage import read_json
path = Path('/results/cpu-constraints.txt')
if not path.exists():
    inventory = read_json('/results/freeze.json')['dependencies']['cpu_dependencies']
    with path.open('x',encoding='utf-8') as handle:
        handle.write(''.join(name+'=='+version+'\n' for name,version in sorted(inventory.items()) if version))
PY
python3 - <<'PY'
from pathlib import Path
import subprocess
path = Path('/results/runtime-packages.txt')
if not path.exists():
    inventory = subprocess.check_output(['python3', '-m', 'pip', 'freeze'], text=True)
    with path.open('x', encoding='utf-8') as handle:
        handle.write(inventory)
PY
python3 -m signir.gpu run --input /input/pairs.jsonl \
  --freeze /results/freeze.json --out /results/run
