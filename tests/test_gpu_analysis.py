from pathlib import Path
import copy
import tempfile
import unittest

from signir.schema import CHECKS, fact, record


def row(identifier, split='diagnostic', number_status='UNKNOWN'):
    checks = {name: {'status': 'UNKNOWN', 'reason': 'unsupported'} for name in CHECKS}
    checks['numbers'] = {'status': number_status, 'reason': 'authored'}
    return {'id': identifier, 'split': split, 'source_group': identifier,
        'english': '3 APPLE', 'gloss': '9 APPLE', 'arms': {
            name: {'status': 'ok', 'checks': copy.deepcopy(checks)} for name in ('cpu', 'structured', 'judge')}}


class GPUAnalysisTests(unittest.TestCase):
    def test_repeat_comparison_requires_identical_pairs_and_exposes_status_changes(self):
        import copy
        from signir.gpu.analysis import compare_runs
        first = row('a',number_status='MATCH')
        second = copy.deepcopy(first)
        second['arms']['judge']['checks']['numbers']['status'] = 'MISMATCH'
        result = compare_runs([first],[second])
        self.assertEqual(result['status_changes'],1)
        self.assertEqual(result['changes'][0]['arm'],'judge')
        second['english'] = 'Different input'
        with self.assertRaises(ValueError):
            compare_runs([first],[second])

    def test_hybrid_controls_identify_gloss_extraction_gain_without_more_calls(self):
        from signir.gpu.analysis import analyze
        item = row('a')
        a, b = record('3 APPLE', 'english', 'authored'), record('9 APPLE', 'gloss', 'authored')
        a['facts']['numbers'] = fact([{'entity': 'APPLE', 'count': 3}], [{'start': 0, 'end': 7, 'text': '3 APPLE'}])
        b['facts']['numbers'] = fact([{'entity': 'APPLE', 'count': 9}], [{'start': 0, 'end': 7, 'text': '9 APPLE'}])
        item['arms']['cpu'].update(english=a, gloss=record('9 APPLE', 'gloss', 'authored'))
        item['arms']['structured'].update(english={'status': 'ok', 'record': a}, gloss={'status': 'ok', 'record': b})
        result = analyze([item])
        self.assertEqual(result['controls']['cpu_english_model_gloss']['counts']['numbers']['MISMATCH'], 1)
        self.assertEqual(result['controls']['model_english_cpu_gloss']['counts']['numbers']['UNKNOWN'], 1)

    def test_all_alarms_are_visible_even_when_known_only_precision_is_perfect(self):
        from signir.gpu.analysis import analyze
        items = [row('a', number_status='MISMATCH'), row('b', number_status='MISMATCH')]
        gold = {'a': {'checks': {'numbers': 'MISMATCH'}}, 'b': {'checks': {'numbers': 'UNKNOWN'}}}
        accounting = analyze(items, gold)['alarm_accountability']['structured']
        self.assertEqual(accounting['total_alarms'], 2)
        self.assertEqual(accounting['confirmed_error_alarms'], 1)
        self.assertEqual(accounting['gold_unknown_alarms'], 1)
        self.assertEqual(accounting['confirmed_fraction_of_all_alarms'], 0.5)

    def test_checks_only_gold_does_not_score_absent_oracle_side_records(self):
        from signir.gpu.analysis import analyze
        gold = {'a': {'checks': {'numbers': 'MISMATCH'}}}
        controls = analyze([row('a')], gold)['controls']
        for name in ('gold_english_model_gloss', 'model_english_gold_gloss'):
            self.assertEqual(controls[name]['eligible_pairs'], 0)
            self.assertEqual(controls[name]['pairs_ineligible'], 1)
            self.assertEqual(controls[name]['pairs_unavailable'], 0)
            self.assertIsNone(controls[name]['quality'])
        self.assertEqual(controls['cpu_english_model_gloss']['eligible_pairs'], 1)
        self.assertEqual(controls['cpu_english_model_gloss']['quality']['numbers']['false_negative'], 1)

    def test_oracle_control_retains_failed_model_side_in_eligible_denominator(self):
        from signir.gpu.analysis import analyze
        gold = {'a': {'checks': {'numbers': 'MISMATCH'},
                      'english': record('3 APPLE', 'english', 'authored')}}
        control = analyze([row('a')], gold)['controls']['gold_english_model_gloss']
        self.assertEqual(control['eligible_pairs'], 1)
        self.assertEqual(control['pairs_available'], 0)
        self.assertEqual(control['pairs_unavailable'], 1)
        self.assertEqual(control['quality']['numbers']['false_negative'], 1)
        self.assertEqual(control['quality']['numbers']['recall'], 0.0)

    def test_evaluation_separates_splits_and_four_supported_fields(self):
        from signir.gpu.evaluation import evaluate
        items = [row('a', 'dev', 'MISMATCH'), row('b', 'test', 'UNKNOWN')]
        gold = {identifier: {'annotation_kind': 'authored', 'checks': {'numbers': 'MISMATCH'}} for identifier in ('a', 'b')}
        result = evaluate(items, gold)
        self.assertEqual(result['arms']['cpu']['possible_supported_checks'], 8)
        self.assertEqual(result['strata']['split']['dev']['arms']['cpu']['quality']['numbers']['recall'], 1.0)
        self.assertEqual(result['strata']['split']['test']['arms']['cpu']['quality']['numbers']['recall'], 0.0)

    def test_challenge_has_distinct_families_and_scope_guards(self):
        from signir.gpu.challenge import build_challenge
        pairs, gold = build_challenge()
        self.assertGreaterEqual(len(pairs), 48)
        self.assertEqual(len(pairs), len(gold))
        self.assertGreaterEqual(len({pair['phenomenon'] for pair in pairs}), 8)
        self.assertTrue(all(item['annotation_kind'] == 'authored' for item in gold))
        absent = [item for item in gold if item['id'].startswith('absent-negation')]
        self.assertTrue(absent)
        self.assertTrue(all(item['checks']['negation'] == 'UNKNOWN' for item in absent))


if __name__ == '__main__':
    unittest.main()
