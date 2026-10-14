import json
from pathlib import Path
import tempfile
import unittest

from signir.data import prepare, validate_pair, import_prior, write_jsonl, read_jsonl
from signir.baselines import sign_f1, word_f1
from signir.controlled import build_fixtures
from signir.evaluate import freeze, evaluate, analyze, calibrate
from signir.correction import correct_once, SavedResponses


def pair(i, english='Alice buys 3 apples.', group=None):
    return {'id': i, 'english': english, 'gloss': 'fs-ALICE BUY 3 APPLE',
            'source_group': group or i, 'provenance': {'kind': 'synthetic', 'version': 'test'}}


class WorkflowTests(unittest.TestCase):
    def test_split_transitive_document_duplicates_and_variants(self):
        rows = [pair('a', group='doc1'), pair('b', group='doc2'),
                pair('c', 'Bob helps Alice.', 'doc2'), pair('d', 'Carol visits Bob.', 'doc3')]
        rows[-1]['variant_of'] = 'c'
        out = prepare(rows)
        self.assertEqual(len({r['split'] for r in out}), 1)
        self.assertEqual(len({r['split_group'] for r in out}), 1)
        self.assertEqual(prepare(list(reversed(rows))), out)

    def test_validation_and_conflicting_presplit_data(self):
        with self.assertRaises(ValueError):
            validate_pair({'english': 'x', 'gloss': 'y'})
        a, b = pair('a'), pair('b')
        a['split'], b['split'] = 'dev', 'test'
        with self.assertRaises(ValueError):
            prepare([a, b])
        with self.assertRaises(ValueError):
            prepare([a, a])

    def test_import_recovers_document_without_positional_guess(self):
        corpus = [{'text': 'Alice helps Bob.', 'gloss': 'fs-ALICE HELP fs-BOB', 'doc_id': 'doc1', 'sent_idx': 4}]
        predictions = [{'source': corpus[0]['text'], 'reference': corpus[0]['gloss'], 'hypothesis': 'fs-BOB HELP fs-ALICE'}]
        out = import_prior(predictions, corpus, {'run_id': 'fixed', 'config': {'llm': {'model': 'saved'}}})
        self.assertEqual(out[0]['document_id'], 'doc1')
        self.assertEqual(out[0]['cohort'], 'natural')
        with self.assertRaises(ValueError):
            import_prior(predictions, corpus + [dict(corpus[0], doc_id='doc2')], {'run_id': 'fixed'})

    def test_baseline_is_lossy_but_multiset(self):
        self.assertEqual(sign_f1('BUY 3 APPLE', 'BUY 9 APPLE'), 1.0)
        self.assertAlmostEqual(sign_f1('APPLE', 'APPLE APPLE'), 2/3)
        self.assertEqual(sign_f1('', ''), 0.0)
        self.assertAlmostEqual(word_f1('BUY 3 APPLE', 'BUY 9 APPLE'), 2/3)

    def test_recoverability_is_reported_without_gold(self):
        p = pair('unknown', 'The complicated source is outside the grammar.')
        report, _ = analyze([p])
        source = next(x for x in report['recoverability'] if x['side'] == 'english' and x['check'] == 'action')
        gloss = next(x for x in report['recoverability'] if x['side'] == 'gloss' and x['check'] == 'action')
        self.assertEqual(source['known'], 0)
        self.assertEqual(gloss['known'], 1)
        self.assertEqual(report['extraction'], [])

    def test_calibration_rejects_test_data(self):
        with self.assertRaises(ValueError):
            calibrate([dict(pair('test'), split='test')])

    def test_false_alarms_only_count_reviewed_unchanged_checks(self):
        p = pair('reviewed')
        p.update(gloss='fs-ALICE BUY 9 APPLE', cohort='reviewed_reference',
                 review={'reviewer': 'test annotator'}, expected={'numbers': 'MATCH'})
        other = dict(p, id='unreviewed', cohort='unreviewed_reference')
        report, _ = analyze([p, other])
        numbers = [r for r in report['summary'] if r['check'] == 'numbers']
        self.assertEqual(sum(r['false_alarms'] for r in numbers), 1)
        self.assertEqual(sum(r['reviewed_unchanged'] for r in numbers), 1)
        self.assertEqual(report['error_attribution']['unresolved'], 2)

    def test_freeze_evaluate_and_tamper_detection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            root = Path(tmp)
            rows = prepare(build_fixtures())
            data = root / 'pairs.jsonl'
            write_jsonl(data, rows)
            lock = root / 'freeze.json'
            freeze(data, lock)
            report = evaluate(data, lock, root / 'out')
            self.assertGreater(report['n_pairs'], 0)
            self.assertTrue((root / 'out' / 'summary.csv').is_file())
            self.assertTrue((root / 'out' / 'records.jsonl').is_file())
            self.assertTrue(report['controlled_errors'])
            frozen = json.loads(lock.read_text())
            self.assertEqual(frozen['calibration_split'], 'dev')
            rows[0]['gloss'] += ' NOT'
            write_jsonl(data, rows)
            with self.assertRaises(ValueError):
                evaluate(data, lock, root / 'tampered')

    def test_correction_is_one_attempt_and_retains_regression(self):
        p = pair('fix')
        p['gloss'] = 'fs-ALICE BUY 9 APPLE'
        calls = []
        def adapter(request):
            calls.append(request)
            return 'fs-BOB BUY 3 APPLE'
        out = correct_once(p, adapter, 'test-fixed')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['original_gloss'], p['gloss'])
        self.assertIn('numbers', out['improved'])
        self.assertIn('entities', out['regressions'])
        self.assertEqual(out['attempts'], 1)
        self.assertEqual(out['before']['gloss']['text'], p['gloss'])
        with self.assertRaises(ValueError):
            correct_once(p, SavedResponses({}), 'fixture')


if __name__ == '__main__':
    unittest.main()
