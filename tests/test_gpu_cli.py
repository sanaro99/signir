import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class GPUCLITests(unittest.TestCase):
    def test_full_authored_workflow_and_warm_cache_resume(self):
        root = Path(__file__).resolve().parents[1]
        fixture = root / 'experiments/dgx-spark/fixtures'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            def command(*args):
                result = subprocess.run([sys.executable, '-m', 'signir.gpu', *map(str, args)],
                    cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            command('freeze', '--input', fixture/'pairs.jsonl', '--revision', 'a'*40,
                    '--container-image', 'replay', '--out', out/'freeze.json')
            for _ in range(2):
                command('replay', '--input', fixture/'pairs.jsonl', '--freeze', out/'freeze.json',
                        '--responses', fixture/'responses.jsonl', '--out', out/'run')
            command('score', '--records', out/'run/records.jsonl', '--gold', fixture/'gold.jsonl', '--out', out/'scored')
            command('annotate', '--input', fixture/'pairs.jsonl', '--out', out/'annotations')
            manifest = json.loads((out/'run/manifest.json').read_text(encoding='utf-8'))
            summary = json.loads((out/'scored/summary.json').read_text(encoding='utf-8'))
            self.assertFalse(manifest['cuda_inference'])
            self.assertEqual(manifest['unique_cached_requests'], 10)
            self.assertEqual(summary['pairs'], 4)
            self.assertEqual(summary['annotation_kinds'], {'authored': 4})
            self.assertEqual(summary['arms']['structured']['quality']['numbers']['true_positive'], 1)
            self.assertEqual(summary['arms']['judge']['quality']['negation']['true_positive'], 2)
            # Blank annotation sheets cannot be silently assembled as human gold.
            result = subprocess.run([sys.executable, '-m', 'signir.gpu', 'assemble',
                '--input', str(fixture/'pairs.jsonl'), '--english', str(out/'annotations/english.jsonl'),
                '--gloss', str(out/'annotations/gloss.jsonl'), '--checks', str(out/'annotations/checks.jsonl'),
                '--out', str(out/'should-not-exist.jsonl')], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((out/'should-not-exist.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
