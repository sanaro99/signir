"""Regressions reproduced while reviewing the merged MISSING/NMM update."""
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from signir import lexicon
from signir.compare import check_pair
from signir.events.audit import audit

ROOT = Path(__file__).resolve().parents[1]


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'experiments/scenario-testing' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScopedComparisonTests(unittest.TestCase):
    def setUp(self):
        lexicon.configure([])

    def tearDown(self):
        lexicon.configure()

    def test_one_gloss_count_cannot_hide_a_conflicting_occurrence(self):
        result = check_pair('Alice buys three books and Bob buys three books.',
                            'fs-ALICE BUY THREE BOOK fs-BOB BUY FIVE BOOK')
        self.assertEqual(result['checks']['numbers']['status'], 'MISMATCH')

    def test_repeated_equal_counts_still_match(self):
        result = check_pair('Alice buys three books and Bob buys three books.',
                            'fs-ALICE BUY THREE BOOK fs-BOB BUY THREE BOOK')
        self.assertEqual(result['checks']['numbers']['status'], 'MATCH')

    def test_reordered_different_counts_need_event_alignment(self):
        result = check_pair('Alice buys three books and Bob buys five books.',
                            'fs-ALICE BUY FIVE BOOK fs-BOB BUY THREE BOOK')
        self.assertEqual(result['checks']['numbers']['status'], 'UNKNOWN')

    def test_single_count_cannot_fulfil_two_occurrences(self):
        result = check_pair('Alice buys three books and Bob buys three books.',
                            'fs-ALICE BUY THREE BOOK fs-BOB BUY BOOK')
        self.assertEqual(result['checks']['numbers']['status'], 'UNKNOWN')

    def test_lexically_ambiguous_attachment_is_not_reused_across_nouns(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'lexicon.json'
            path.write_text(json.dumps({'volume': ['BOOK']}))
            lexicon.configure([path])
            result = check_pair('Alice buys three books and two volumes.', 'fs-ALICE BUY THREE BOOK')
            self.assertEqual(result['checks']['numbers']['status'], 'UNKNOWN')

    def test_negation_on_a_different_predicate_is_unresolved(self):
        result = check_pair('Alice does not buy apples but Bob sells books.',
                            'fs-ALICE BUY APPLE fs-BOB NOT SELL BOOK', {'negation': False})
        self.assertEqual(result['checks']['negation']['status'], 'UNKNOWN')

    def test_repeated_predicate_negation_requires_occurrence_alignment(self):
        result = check_pair('Alice does not buy apples but Bob buys books.',
                            'fs-ALICE BUY APPLE fs-BOB NOT BUY BOOK', {'negation': False})
        self.assertEqual(result['checks']['negation']['status'], 'UNKNOWN')

    def test_sentence_nmm_cannot_resolve_multiple_events(self):
        result = check_pair('Alice does not buy apples but Bob sells books.',
                            'fs-ALICE BUY APPLE fs-BOB SELL BOOK', {'negation': True})
        self.assertEqual(result['checks']['negation']['status'], 'UNKNOWN')

    def test_negation_presence_without_a_recognized_predicate_is_unresolved(self):
        for gloss, nmm in (('fs-ALICE NOT APPLE', None),
                           ('fs-ALICE QXYZ APPLE', {'negation': True})):
            with self.subTest(gloss=gloss):
                result = check_pair('Alice does not buy apples.', gloss, nmm)['checks']['negation']
                self.assertEqual(result['status'], 'UNKNOWN')
                self.assertTrue(result['marker_presence']['english'])
                self.assertTrue(result['marker_presence']['gloss_manual'] or
                                result['marker_presence']['gloss_nmm'])

    def test_adjacent_negator_supports_a_have_predicate_reading(self):
        result = check_pair('We should not have to rely on newspapers.',
                            'X-WE SHOULD DESC-NOT HAVE TO RELY ON NEWSPAPER', notation='aslg_pc12')
        self.assertEqual(result['gloss']['facts']['negation']['value'],
                         {'action': 'HAVE', 'negative': True})
        self.assertEqual(result['checks']['negation']['status'], 'MATCH')

    def test_negative_quantity_requires_one_unambiguous_noun_occurrence(self):
        for english, gloss in (
                ('I have no money.', 'IX-1p BOOK NONE/NOTHING'),
                ('I have money and no books.', 'IX-1p MONEY NONE/NOTHING BOOK'),
                ('I have no money.', 'IX-1p MONEY NONE/NOTHING QXYZ'),
                ('I have no money.', 'IX-1p MONEY NONE/NOTHING MONEY')):
            with self.subTest(english=english, gloss=gloss):
                result = check_pair(english, gloss)
                self.assertEqual(result['checks']['negation']['status'], 'UNKNOWN')

    def test_explicit_scope_of_a_unique_predicate_remains_supported(self):
        result = check_pair('Alice does not buy apples but Bob sells books.',
                            'fs-ALICE NOT BUY APPLE fs-BOB SELL BOOK', {'negation': False})
        self.assertEqual(result['checks']['negation']['status'], 'MATCH')


class PairedAuditCompatibilityTests(unittest.TestCase):
    def test_missing_is_an_assessed_legacy_baseline_status(self):
        source = {'english': 'Alice buys books.', 'gloss': 'BUY BOOK'}
        records = [{'id': 'one', 'source': source, 'state': 'ok', 'checks': [
            {'field': 'alignment', 'status': 'UNKNOWN', 'reason': 'unmatched_event'}]}]
        baseline = [{'id': 'one', 'source': source, 'checks': {
            'entities': {'status': 'MISSING', 'reason': 'Not expressed'}}}]
        result = audit(records, baseline=baseline)
        self.assertEqual(result['baseline']['check_counts']['MISSING'], 1)
        self.assertEqual(result['baseline']['any_assessed_pairs'], 1)
        self.assertEqual(result['paired_transitions'], {'assessed->all_unknown': 1})

    def test_baseline_compatibility_does_not_change_event_or_label_contract(self):
        source = {'english': 'E', 'gloss': 'G'}
        row = {'id': 'one', 'source': source, 'state': 'ok', 'checks': [
            {'field': 'numbers', 'status': 'MISSING'}]}
        with self.assertRaises(ValueError):
            audit([row])
        row['checks'][0]['status'] = 'UNKNOWN'
        labels = [{'id': 'one', **source, 'reviewer': 'independent tester',
                   'annotation_source': 'independent_human',
                   'checks': [{'field': 'numbers', 'status': 'MISSING'}]}]
        with self.assertRaises(ValueError):
            audit([row], labels=labels)


class ScenarioReportingTests(unittest.TestCase):
    def setUp(self):
        lexicon.configure([])
        self.scenario = load_script('review_scenarios', 'run_scenarios.py')

    def tearDown(self):
        lexicon.configure()

    def row(self, english='The kids play.', gloss='CHILDREN PLAY'):
        return {'id': 'authored', 'cohort': 'authored_review', 'english': english, 'gloss': gloss,
                'gloss_nmm': {'negation': False}, 'notation': None, 'gold_negation': False}

    def test_unchanged_control_exposes_total_and_incremental_alarms(self):
        summary, _ = self.scenario.corrupted([self.row()], [])
        control = summary['authored_review']['control_unchanged']
        self.assertEqual(control.get('any_flag'), 1)
        self.assertEqual(control['any_new_flag'], 0)
        self.assertEqual(control.get('base_any_flag'), 1)

    def test_existing_target_alarm_is_not_a_new_detection(self):
        summary, _ = self.scenario.corrupted([self.row()], [])
        swap = summary['authored_review']['entity_swapped']
        self.assertEqual(swap['flagged_MISSING'], 1)
        self.assertEqual(swap.get('target_already_flagged'), 1)
        self.assertEqual(swap.get('new_target_flag'), 0)
        self.assertIsNone(swap.get('new_target_flag_rate'))

    def test_new_target_detection_retains_its_eligible_denominator(self):
        summary, _ = self.scenario.corrupted([self.row('The dog sleeps.', 'DOG SLEEP')], [])
        swap = summary['authored_review']['entity_swapped']
        self.assertEqual(swap.get('target_already_flagged'), 0)
        self.assertEqual(swap.get('new_target_flag'), 1)
        self.assertEqual(swap.get('new_target_flag_rate'), 1.0)


class CorrectionSelectionTests(unittest.TestCase):
    def test_zero_selected_rows_publish_unmeasured_averages_without_inference(self):
        correction = load_script('review_correction', 'correct_flagged.py')
        correct = {'source': 'Alice buys 3 apples.', 'hypothesis': 'fs-ALICE BUY 3 APPLE',
                   'reference': 'fs-ALICE BUY 3 APPLE', 'nmm': {'negation': False}}
        skipped = {**correct, 'hypothesis': ''}
        for predictions in ([], [correct], [skipped]):
            with self.subTest(predictions=predictions), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                source, output = directory / 'predictions.jsonl', directory / 'out'
                source.write_text(''.join(json.dumps(row) + '\n' for row in predictions))
                argv = ['correct_flagged.py', '--predictions', str(source), '--out', str(output),
                        '--gold', str(directory / 'absent-gold')]
                with patch('sys.argv', argv), redirect_stdout(io.StringIO()), patch.object(
                        correction.LocalClient, 'extract', side_effect=AssertionError('Unexpected inference')):
                    correction.main()
                summary = json.loads((output / 'summary.json').read_text())
                self.assertEqual(summary['flagged_pairs'], 0)
                self.assertIsNone(summary['mean_word_f1_before'])
                for arm in ('rules', 'generic', 'signir'):
                    self.assertIsNone(summary[arm]['mean_sign_f1_before'])
                    self.assertIsNone(summary[arm]['mean_sign_f1_after'])
                    self.assertEqual(summary[arm]['model_errors'], 0)
                self.assertEqual((output / 'records.jsonl').read_text(), '')
