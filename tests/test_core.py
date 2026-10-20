import unittest

from signir.compare import check_pair, compare
from signir.english import extract_english
from signir.gloss import extract_gloss


class CoreTests(unittest.TestCase):
    def statuses(self, english, gloss):
        return {k: v['status'] for k, v in check_pair(english, gloss)['checks'].items()}

    def test_supported_match_with_evidence(self):
        result = check_pair('Alice does not buy 3 apples.',
                            'AGENT:fs-ALICE BUY PATIENT:APPLE 3 APPLE NEG:BUY')
        self.assertEqual(set(x['status'] for x in result['checks'].values()), {'MATCH'})
        for side in ('english', 'gloss'):
            ir = result[side]
            for field in ir['facts'].values():
                for span in field['evidence']:
                    self.assertEqual(ir['text'][span['start']:span['end']], span['text'])

    def test_absent_negative_marker_without_nmm_is_unknown(self):
        # Negation may be a head-shake only, so a gloss without NMM labels cannot show it is missing.
        s = self.statuses('Alice does not buy 3 apples.', 'fs-ALICE BUY 3 APPLE')
        self.assertEqual(s['negation'], 'UNKNOWN')
        self.assertEqual(s['roles'], 'MATCH')

    def test_negation_uses_non_manual_markers(self):
        e, g = 'Alice does not buy 3 apples.', 'fs-ALICE BUY 3 APPLE'
        status = lambda nmm, notation=None: check_pair(e, g, nmm, notation)['checks']['negation']['status']
        self.assertEqual(status({'negation': True}), 'MATCH')
        self.assertEqual(status({'negation': False}), 'MISSING')
        self.assertEqual(status(None, 'aslg_pc12'), 'MISSING')
        added = check_pair('Alice buys 3 apples.', g, {'negation': True})['checks']['negation']
        self.assertEqual(added['status'], 'MISMATCH')
        self.assertIn({'channel': 'nmm', 'label': 'negation', 'value': True}, added['gloss_evidence'])
        annotated = check_pair(e, 'AGENT:fs-ALICE BUY PATIENT:APPLE 3 APPLE', {'negation': False})
        self.assertEqual(annotated['checks']['negation']['status'], 'MISSING')

    def test_explicit_opposite_polarity(self):
        self.assertEqual(self.statuses('Alice does not buy apples.',
                                      'fs-ALICE BUY APPLE POS:BUY')['negation'], 'MISMATCH')

    def test_negation_wrong_action_is_unknown(self):
        self.assertEqual(self.statuses('Alice does not buy apples.',
                                      'fs-ALICE BUY APPLE NEG:SELL')['negation'], 'UNKNOWN')

    def test_multi_clause_scopes_explicit_negation_without_guessing_gloss(self):
        ir = extract_english('Alice does not say Bob buys apples.')
        self.assertEqual(ir['facts']['action']['state'], 'UNKNOWN')
        self.assertEqual(ir['facts']['negation']['value'], {'action': 'SAY', 'negative': True})
        self.assertEqual(extract_gloss('fs-ALICE BUY NOT fs-BOB SELL')['facts']['negation']['state'], 'UNKNOWN')

    def test_number_attachment_is_not_bag_of_numbers(self):
        s = self.statuses('Alice buys 3 apples and 2 books.', 'fs-ALICE BUY 2 APPLE 3 BOOK')
        self.assertEqual(s['numbers'], 'MISMATCH')

    def test_roles_from_annotations_or_plain_word_order(self):
        e = 'Alice helps Bob.'
        self.assertEqual(self.statuses(e, 'fs-BOB HELP fs-ALICE')['roles'], 'MISMATCH')
        self.assertEqual(self.statuses(e, 'fs-ALICE HELP fs-BOB')['roles'], 'MATCH')
        # A topic marker or a directional verb with loci blocks the word-order reading.
        topic = check_pair(e, 'fs-BOB HELP fs-ALICE', {'topic': True})['checks']['roles']
        self.assertEqual(topic['status'], 'UNKNOWN')
        self.assertEqual(self.statuses(e, 'fs-BOB i:HELP:j fs-ALICE')['roles'], 'UNKNOWN')
        s = self.statuses(e, 'AGENT:fs-BOB HELP PATIENT:fs-ALICE POS:HELP')
        self.assertEqual(s['roles'], 'MISMATCH')
        self.assertEqual(s['entities'], 'MATCH')

    def test_missing_and_unrecognized_evidence(self):
        for gloss in ('', 'IX-1p GIVE:i/j (2h)BOOK'):
            self.assertEqual(self.statuses('Alice buys 3 apples.', gloss)['numbers'], 'MISSING')
        self.assertEqual(self.statuses('Alice buys 3 apples.', 'fs-ALICE BUY 3 UNKNOWN-LABEL')['numbers'], 'UNKNOWN')

    def test_preserve_tokens_and_repetitions(self):
        ir = extract_gloss('fs-A-L-I-C-E BUY 3 APPLE APPLE GIVE:i/j')
        self.assertEqual(ir['tokens'], ['fs-A-L-I-C-E', 'BUY', '3', 'APPLE', 'APPLE', 'GIVE:i/j'])
        s = self.statuses('Alice buys apples.', 'fs-ALICE BUY APPLE APPLE')
        self.assertEqual(s['entities'], 'MATCH')  # repetition can mark plural in ASL
        self.assertEqual(extract_gloss('fs-ALICE BUY APPLE APPLE')['facts']['entities']['value'], ['NAME:ALICE', 'APPLE', 'APPLE'])

    def test_dropped_entity_or_count_is_missing(self):
        s = check_pair('Alice buys two apples.', 'BUY TWO APPLE')['checks']['entities']
        self.assertEqual((s['status'], s['missing']), ('MISSING', ['NAME:ALICE']))
        self.assertEqual(self.statuses('Alice buys two apples and three books.', 'fs-ALICE BUY TWO APPLE BOOK')['numbers'], 'MISSING')
        self.assertEqual(self.statuses('Alice buys two apples.', 'fs-ALICE BUY APPLE TWO')['numbers'], 'UNKNOWN')

    def test_merged_numerals_count(self):
        self.assertEqual(self.statuses('My son is 7 years old.', 'POSS-1p SON AGE-SEVEN')['numbers'], 'MATCH')
        self.assertEqual(self.statuses('My son is 7 years old.', 'POSS-1p SON AGE-SEVEN')['entities'], 'MATCH')
        self.assertEqual(self.statuses('We stayed for two weeks.', 'IX-1p STAY TWO-WEEK')['numbers'], 'MATCH')
        self.assertEqual(self.statuses('We stayed for two weeks.', 'IX-1p STAY THREE-WEEK')['numbers'], 'MISMATCH')

    def test_pronouns_are_not_proper_names(self):
        ir = extract_english('She buys apples.')
        self.assertEqual(ir['facts']['entities']['value'], ['APPLE'])
        self.assertEqual(ir['facts']['roles']['state'], 'UNKNOWN')

    def test_counts_need_same_entity_alignment(self):
        statuses = self.statuses('Alice buys two apples.', 'fs-ALICE BUY TWO BOOK')
        self.assertEqual(statuses['entities'], 'MISSING')
        self.assertEqual(statuses['numbers'], 'UNKNOWN')

    def test_unsupported_numeric_labels_abstain(self):
        self.assertEqual(self.statuses('Alice buys two apples.', 'fs-ALICE BUY \u00b2 APPLE')['numbers'], 'UNKNOWN')

    def test_comparator_only_uses_records(self):
        a, b = extract_english('Alice helps Bob.'), extract_gloss('AGENT:fs-ALICE HELP PATIENT:fs-BOB POS:HELP')
        self.assertEqual(compare(a, b), compare(a, b))
        b['version'] = 'unsupported'
        with self.assertRaises(ValueError):
            compare(a, b)


if __name__ == '__main__':
    unittest.main()
