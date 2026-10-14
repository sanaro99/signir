import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        p = subprocess.run([sys.executable, '-m', 'signir', *map(str, args)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_demo_and_pair_json(self):
        text = self.run_cli('demo')
        self.assertIn('MISMATCH', text)
        self.assertIn('UNKNOWN', text)
        obj = json.loads(self.run_cli('check', '--english', 'Alice buys 3 apples.', '--gloss', 'fs-ALICE BUY 9 APPLE', '--json'))
        self.assertEqual(obj['checks']['numbers']['status'], 'MISMATCH')

    def test_complete_cli_workflow(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            root = Path(tmp)
            raw, prepared, lock = root/'raw.jsonl', root/'pairs.jsonl', root/'lock.json'
            self.run_cli('build-controlled', '--out', raw)
            self.run_cli('prepare', raw, '--out', prepared)
            self.run_cli('check-file', prepared, '--out', root/'checks')
            self.run_cli('freeze', prepared, '--out', lock)
            self.run_cli('evaluate', prepared, '--freeze', lock, '--out', root/'evaluation')
            self.run_cli('feasibility', prepared, '--out', root/'feasibility')
            self.assertEqual(len((root/'evaluation'/'records.jsonl').read_text().splitlines()), 32)
            self.run_cli('correct', Path(__file__).resolve().parents[1]/'signir'/'fixtures'/'correction-inputs.jsonl',
                         '--responses', Path(__file__).resolve().parents[1]/'signir'/'fixtures'/'corrections.json', '--out', root/'corrections')
            records = [json.loads(x) for x in (root/'corrections'/'records.jsonl').read_text().splitlines()]
            self.assertEqual(len(records), 2)
            self.assertTrue(any(x['regressions'] for x in records))


if __name__ == '__main__':
    unittest.main()
