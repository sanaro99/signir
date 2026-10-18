"""Publish an authored CUDA suite only after complete, fingerprinted scoring."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .challenge import build_challenge, write_challenge
from .storage import file_hash, read_json, write_json

ARTIFACTS = ('summary.json', 'analysis.json', 'report.md', 'review_queue.jsonl', 'checks.csv')


def verify_scored(output, records, gold):
    marker = output/'complete.json'
    if not marker.is_file() or not all((output/name).is_file() for name in ARTIFACTS):
        raise ValueError('Incomplete scored output; preserve it and use a new suite directory')
    complete = read_json(marker)
    expected = {'records_sha256': file_hash(records), 'gold_sha256': file_hash(gold)}
    if (complete.get('provenance') != expected or
            complete.get('artifacts') != {name: file_hash(output/name) for name in ARTIFACTS}):
        raise ValueError('Changed scored output or inputs; use a new suite directory')


def run_suite(output, config=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    config = Path(config).resolve() if config else root/'experiments/dgx-spark/config.json'
    challenge, scored = output/'challenge', output/'scored'
    pairs, gold = challenge/'pairs.jsonl', challenge/'gold.jsonl'
    records = output/'inference/run/records.jsonl'
    if challenge.exists():
        if not pairs.is_file() or not gold.is_file():
            raise ValueError('Incomplete challenge; preserve it and use a new suite directory')
        actual = [[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
                  for path in (pairs, gold)]
        if actual != list(build_challenge()):
            raise ValueError('Changed challenge; use a new suite directory')
    else:
        # Interrupted creation leaves only an isolated temporary directory.
        with tempfile.TemporaryDirectory(prefix='.challenge-', dir=output) as temporary:
            write_challenge(temporary)
            Path(temporary).rename(challenge)
    if scored.exists():
        verify_scored(scored, records, gold)  # Reject partial/stale reports before GPU setup.
    status = subprocess.run(['bash', str(root/'experiments/dgx-spark/run.sh'),
        str(pairs), str(output/'inference'), str(config)], check=False).returncode
    if status not in (0, 3):
        return status
    if scored.exists():
        verify_scored(scored, records, gold)
    else:
        with tempfile.TemporaryDirectory(prefix='.scored-', dir=output) as temporary:
            from .__main__ import main
            status_score = main(['score', '--records', str(records), '--gold', str(gold), '--out', temporary])
            if status_score:
                return status_score
            temporary = Path(temporary)
            summary = read_json(temporary/'summary.json')
            write_json(temporary/'complete.json', {'provenance': summary['provenance'],
                'artifacts': {name: file_hash(temporary/name) for name in ARTIFACTS}})
            verify_scored(temporary, records, gold)
            temporary.rename(scored)
    print('Authored diagnostic results:', scored/'report.md')
    return status


if __name__ == '__main__':
    try:
        if not 2 <= len(sys.argv) <= 3:
            raise ValueError('Usage: python -m signir.gpu.suite OUTPUT_DIRECTORY [CONFIG.json]')
        status = run_suite(*sys.argv[1:])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('Challenge error: ' + str(exc), file=sys.stderr)
        status = 2
    raise SystemExit(status)
