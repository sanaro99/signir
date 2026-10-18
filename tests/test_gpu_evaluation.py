import json
from pathlib import Path
import tempfile
import unittest

from signir.schema import CHECKS, fact, record


def prediction(identifier, number_status):
    checks = {key: {'status': 'UNKNOWN', 'reason': 'unsupported'} for key in CHECKS}
    checks['numbers'] = {'status': number_status, 'reason': 'authored'}
    return {'id': identifier, 'english': 'Alice buys apples.', 'gloss': 'fs-ALICE BUY APPLE',
            'arms': {arm: {'status': 'ok', 'checks': checks} for arm in ('cpu', 'structured', 'judge')}}


class GPUEvaluationTests(unittest.TestCase):
    def test_unknown_predictions_are_missed_errors_and_unlabeled_rows_are_not_negatives(self):
        from signir.gpu.evaluation import evaluate
        rows = [prediction('a', 'UNKNOWN'), prediction('b', 'MATCH'), prediction('unlabeled', 'MISMATCH')]
        gold = {'a': {'checks': {'numbers': 'MISMATCH'}}, 'b': {'checks': {'numbers': 'MATCH'}}}
        result = evaluate(rows, gold)
        metrics = result['arms']['structured']['quality']['numbers']
        self.assertEqual(metrics['labeled_known'], 2)
        self.assertEqual(metrics['false_negative'], 1)
        self.assertEqual(metrics['true_negative'], 1)
        self.assertEqual(metrics['false_positive'], 0)
        self.assertEqual(metrics['recall'], 0.0)
        self.assertEqual(metrics['accuracy_including_abstentions'], 0.5)

    def test_no_gold_does_not_produce_accuracy(self):
        from signir.gpu.evaluation import evaluate
        result = evaluate([prediction('a', 'MATCH')])
        self.assertIsNone(result['arms']['cpu']['quality'])
        self.assertIsNone(result['extraction'])
        self.assertEqual(result['arms']['cpu']['assessed_checks'], 1)

    def test_assertions_on_gold_unknowns_are_visible(self):
        from signir.gpu.evaluation import evaluate
        result = evaluate([prediction('a', 'MATCH')], {'a': {'checks': {'numbers': 'UNKNOWN'}}})
        metrics = result['arms']['judge']['quality']['numbers']
        self.assertEqual(metrics['asserted_on_gold_unknown'], 1)
        self.assertEqual(metrics['labeled_known'], 0)
        self.assertIsNone(metrics['accuracy_including_abstentions'])

    def test_failed_judgments_remain_in_denominator(self):
        from signir.gpu.evaluation import evaluate
        row = prediction('a', 'UNKNOWN')
        row['arms']['judge']['status'] = 'error'
        result = evaluate([row], {'a': {'checks': {'numbers': 'MISMATCH'}}})
        self.assertEqual(result['arms']['judge']['failed_pairs'], 1)
        self.assertEqual(result['arms']['judge']['quality']['numbers']['false_negative'], 1)

    def test_gold_contract_control_is_separate_from_model_extraction(self):
        from signir.gpu.evaluation import evaluate
        a = record('3 APPLE', 'english', 'authored')
        b = record('9 APPLE', 'gloss', 'authored')
        a['facts']['numbers'] = fact([{'entity': 'APPLE', 'count': 3}],
            [{'start': 0, 'end': 7, 'text': '3 APPLE'}])
        b['facts']['numbers'] = fact([{'entity': 'APPLE', 'count': 9}],
            [{'start': 0, 'end': 7, 'text': '9 APPLE'}])
        result = evaluate([prediction('a', 'UNKNOWN')],
            {'a': {'english': a, 'gloss': b, 'checks': {'numbers': 'MISMATCH'}}})
        self.assertEqual(result['gold_contract_control']['numbers']['true_positive'], 1)
        self.assertEqual(result['arms']['structured']['quality']['numbers']['false_negative'], 1)

    def test_annotation_sheets_exclude_other_side_and_existing_labels(self):
        from signir.gpu.evaluation import export_annotations
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.jsonl'
            source.write_text(json.dumps({'id': 'a', 'english': 'SOURCE SECRET', 'gloss': 'TARGET SECRET',
                'source_group': 'doc', 'gold': 'GOLD SECRET'}) + '\n', encoding='utf-8')
            export_annotations(source, root / 'sheets')
            english = (root / 'sheets' / 'english.jsonl').read_text(encoding='utf-8')
            gloss = (root / 'sheets' / 'gloss.jsonl').read_text(encoding='utf-8')
            self.assertNotIn('TARGET SECRET', english)
            self.assertNotIn('SOURCE SECRET', gloss)
            self.assertNotIn('GOLD SECRET', english + gloss)
            self.assertEqual(json.loads(english)['annotation_kind'], 'unreviewed')

    def test_gold_requires_matching_texts_review_status_and_unique_ids(self):
        from signir.gpu.evaluation import load_gold
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gold.jsonl'
            row = {'id': 'a', 'annotation_kind': 'unreviewed', 'checks': {'numbers': 'MATCH'}}
            path.write_text(json.dumps(row) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_gold(path, [prediction('a', 'MATCH')])

    def test_checks_only_gold_is_bound_to_the_exact_pair(self):
        from signir.gpu.evaluation import load_gold
        from signir.gpu.storage import digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gold.jsonl'
            row = {'id': 'a', 'annotation_kind': 'authored', 'checks': {'numbers': 'MATCH'}}
            path.write_text(json.dumps(row) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_gold(path, [prediction('a', 'MATCH')])
            row['pair_sha256'] = digest({'english': 'Alice buys apples.', 'gloss': 'fs-ALICE BUY APPLE'})
            path.write_text(json.dumps(row) + '\n', encoding='utf-8')
            self.assertEqual(load_gold(path, [prediction('a', 'MATCH')])['a']['checks'], {'numbers': 'MATCH'})
            row.update(annotation_kind='authored', english=record('different', 'english', 'authored'))
            path.write_text(json.dumps(row) + '\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_gold(path, [prediction('a', 'MATCH')])


if __name__ == '__main__':
    unittest.main()
