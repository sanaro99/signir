import csv
import json
from pathlib import Path
import tempfile
import unittest

from signir import heldout
from signir.data import read_jsonl, write_jsonl


def corpus_row(text, gloss, doc, source='asllrp', i=0):
    return {'text': text, 'gloss': gloss, 'source': source, 'doc_id': doc, 'sent_idx': i}


def make_data(root):
    """Tiny corpus: doc-dev is used in development; doc-shared repeats a development sentence."""
    data = Path(root) / 'data'
    dev = [corpus_row('Alice buys three apples today.', 'fs-ALICE BUY THREE APPLE', 'doc-dev')]
    pool = [corpus_row('Bob does not like dogs at all.', 'fs-BOB NOT LIKE DOG', 'doc-new', i=1),
            corpus_row('Carol sees two cats outside.', 'fs-CAROL SEE TWO CAT', 'doc-new', i=2),
            corpus_row('The teacher helps the student.', 'TEACHER HELP STUDENT', 'doc-new', i=3),
            corpus_row('Alice buys three apples today.', 'fs-ALICE BUY THREE APPLE', 'doc-shared'),
            corpus_row('Dana visits the old school.', 'fs-DANA VISIT OLD SCHOOL', 'doc-shared', i=1),
            corpus_row('My brother never drives fast.', 'BROTHER NEVER DRIVE FAST', 'story_a_1001_small_0',
                       'ncslgr'),
            corpus_row('My sister reads four books.', 'SISTER READ FOUR BOOK', 'story_a_1002_small_1',
                       'ncslgr')]
    for name in heldout.ASLLRP_FILES + heldout.NCSLGR_FILES:
        rows = dev if name in heldout.DEVELOPMENT_FILES else []
        if name == 'processed/asllrp/example_pool.jsonl':
            rows = [r for r in pool if r['source'] == 'asllrp']
        if name == 'processed/ncslgr/test.jsonl':
            rows = [r for r in pool if r['source'] == 'ncslgr']
        write_jsonl(data / name, rows)
    (data / 'dai').mkdir()
    (data / 'raw' / 'ncslgr' / 'elanBUcorpus').mkdir(parents=True)
    return data


def fill(sheet, labels):
    with open(sheet, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0])
    for r in rows:
        r.update({k: labels.get(k, 'ok') for k in heldout.CHECKS}, meaning_preserved='yes')
    with open(sheet, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)


class HeldoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = make_data(self.root)
        self.out = self.root / 'heldout'
        self.manifest = self.root / 'manifest.json'
        self.m = heldout.build(self.data, self.out, self.manifest, target=10)

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_reserves_only_untouched_groups_and_seals_hashes(self):
        self.assertEqual(self.m['reserved_groups'], ['asllrp:doc-new', 'ncslgr:story_a'])
        pairs = read_jsonl(self.out / 'pairs.jsonl')
        self.assertEqual(len(pairs), 5)
        self.assertFalse({'doc-dev', 'doc-shared'} & {p['doc_id'] for p in pairs})
        self.assertEqual(json.loads(self.manifest.read_text())['pairs_sha256'], self.m['pairs_sha256'])
        with self.assertRaises(ValueError):
            heldout.build(self.data, self.out, None)  # never overwrite a sealed set

    def test_guard_rejects_reserved_development_rows(self):
        heldout.assert_not_reserved([{'source': 'asllrp', 'doc_id': 'doc-dev'}], self.manifest)
        with self.assertRaises(ValueError):
            heldout.assert_not_reserved([{'source': 'ncslgr', 'doc_id': 'story_a_1001_small_0'}], self.manifest)

    def test_sheets_are_blind_and_adjudication_produces_gold(self):
        sheets = self.root / 'sheets'
        heldout.sheets(self.out, sheets)
        header = (sheets / 'sheet-A.csv').read_text(encoding='utf-8-sig').splitlines()[0]
        self.assertNotIn('system', header)
        self.assertNotIn('status', header)
        fill(sheets / 'sheet-A.csv', {'negation': 'ok'})
        fill(sheets / 'sheet-B.csv', {'negation': 'omitted'})
        first = heldout.adjudicate(sheets / 'key.csv', [sheets / 'sheet-A.csv', sheets / 'sheet-B.csv'],
                                   self.root / 'adj-1')
        self.assertEqual(first['unresolved'], 5)
        self.assertFalse((self.root / 'adj-1' / 'gold.jsonl').exists())
        resolved = self.root / 'adj-1' / 'disagreements.csv'
        with open(resolved, encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r['final'] = 'ok'
        with open(resolved, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        heldout.adjudicate(sheets / 'key.csv', [sheets / 'sheet-A.csv', sheets / 'sheet-B.csv'],
                           self.root / 'adj-2', resolved)
        gold = read_jsonl(self.root / 'adj-2' / 'gold.jsonl')
        self.assertEqual(len(gold), 5)
        self.assertTrue(all(g['labels']['negation'] == 'ok' for g in gold))

    def test_invalid_labels_are_rejected(self):
        sheets = self.root / 'sheets'
        heldout.sheets(self.out, sheets)
        fill(sheets / 'sheet-A.csv', {'numbers': 'maybe'})
        fill(sheets / 'sheet-B.csv', {})
        with self.assertRaises(ValueError):
            heldout.adjudicate(sheets / 'key.csv', [sheets / 'sheet-A.csv', sheets / 'sheet-B.csv'], self.root / 'x')

    def test_candidates_and_rates(self):
        predictions = self.root / 'run.jsonl'
        write_jsonl(predictions, [{'source': 'Bob does not like dogs at all.', 'hypothesis': 'fs-BOB LIKE DOG',
                                   'nmm': {'negation': False}}])
        result = heldout.add_candidates(self.out, predictions, 'model-x', self.root / 'cands.jsonl')
        self.assertEqual(result['added'], 1)
        cands = read_jsonl(self.root / 'cands.jsonl')
        self.assertEqual(len({c['item_id'] for c in cands}), 6)
        rates = heldout._rates([('omitted', 'MISSING', 'high'), ('ok', 'MISSING', 'low'),
                                ('ok', 'MATCH', None), ('changed', 'UNKNOWN', None), ('unclear', 'MISMATCH', 'high')],
                               lambda x: x[1] in heldout.ALARMS)
        self.assertEqual((rates['true_alarms'], rates['false_alarms'], rates['gold_unclear_excluded']), (1, 1, 1))
        self.assertEqual(rates['recall'], 0.5)
        self.assertEqual(rates['missed_as_UNKNOWN'], 1)

    def test_score_end_to_end_counts_reference_alarms(self):
        sheets = self.root / 'sheets'
        heldout.sheets(self.out, sheets)
        for name in ('A', 'B'):
            fill(sheets / f'sheet-{name}.csv', {})
        heldout.adjudicate(sheets / 'key.csv', [sheets / 'sheet-A.csv', sheets / 'sheet-B.csv'], self.root / 'adj')
        report = heldout.score(self.out, self.root / 'adj' / 'gold.jsonl', self.manifest, self.root / 'score')
        negation = report['systems']['reference']['negation']['all_alarms']
        self.assertEqual(negation['gold_errors'], 0)
        self.assertEqual(negation['n'], 5)
        self.assertIsNotNone(report['checker']['extraction'])

    def test_score_refuses_changed_pairs(self):
        (self.out / 'pairs.jsonl').write_text('{}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            heldout.score(self.out, self.root / 'gold.jsonl', self.manifest, self.root / 'score')


if __name__ == '__main__':
    unittest.main()
