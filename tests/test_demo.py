"""The demo must run the real checker and ship authored examples only."""
import importlib.util
import json
from pathlib import Path
import unittest

DEMO = Path(__file__).resolve().parents[1] / 'demo'
spec = importlib.util.spec_from_file_location('signir_demo_server', DEMO / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class DemoTests(unittest.TestCase):
    def test_result_is_the_checker_output_with_valid_evidence(self):
        from signir.compare import check_pair
        body = {'english': 'Bob does not like dogs.', 'gloss': 'fs-BOB LIKE DOG', 'nmm': {'negation': False},
                'reference': 'fs-BOB NOT LIKE DOG'}
        result = server.run_check(body)
        expected = check_pair(body['english'], body['gloss'], body['nmm'])['checks']
        self.assertEqual({k: v['status'] for k, v in result['checks'].items()},
                         {k: v['status'] for k, v in expected.items()})
        self.assertEqual(result['checks']['negation']['status'], 'MISSING')
        self.assertEqual(result['baseline']['sign_f1'], 0.857)
        self.assertEqual(result['graphs']['gloss']['nonmanual'], [{'label': 'negation', 'value': False}])
        for check in result['checks'].values():
            for side in ('english', 'gloss'):
                for span in check[side + '_evidence']:
                    if 'start' in span:
                        self.assertEqual(result[side][span['start']:span['end']], span['text'])

    def test_every_example_runs_and_groups_keep_their_promise(self):
        alarms = {}
        for group in server.examples()['groups']:
            for example in group['examples']:
                result = server.run_check({k: example.get(k) for k in ('english', 'gloss', 'nmm', 'notation', 'reference')})
                alarms[example['id']] = [c['status'] for c in result['checks'].values() if c['status'] in ('MISMATCH', 'MISSING')]
                if group['id'] == 'errors':
                    self.assertTrue(alarms[example['id']], example['id'])
                    self.assertGreaterEqual(result['baseline']['sign_f1'], 0.6)
                if group['id'] in ('faithful', 'unknown'):
                    self.assertEqual(alarms[example['id']], [], example['id'])
        # The weak spots are shown as they are: one false alarm and one missed error.
        self.assertTrue(alarms['false-alarm'])
        self.assertEqual(alarms['missed'], [])

    def test_bad_input_is_rejected(self):
        for body in ([], {}, {'english': 'a', 'gloss': ' '}, {'english': 'a' * 601, 'gloss': 'A'},
                     {'english': 'a', 'gloss': 'A', 'nmm': {'negation': 'yes'}},
                     {'english': 'a', 'gloss': 'A', 'nmm': {'other': True}},
                     {'english': 'a', 'gloss': 'A', 'notation': 'unknown'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                server.run_check(body)

    def test_examples_are_marked_authored(self):
        data = json.loads((DEMO / 'examples.json').read_text(encoding='utf-8'))
        self.assertIn('Authored', data['note'])
        ids = [e['id'] for g in data['groups'] for e in g['examples']]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == '__main__':
    unittest.main()
