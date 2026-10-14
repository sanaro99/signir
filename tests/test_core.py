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

    def test_absent_negative_marker_is_unknown(self):
        s = self.statuses('Alice does not buy 3 apples.', 'fs-ALICE BUY 3 APPLE')
        self.assertEqual(s['negation'], 'UNKNOWN')
        self.assertEqual(s['roles'], 'UNKNOWN')

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

    def test_roles_require_annotations_and_detect_reversal(self):
        e = 'Alice helps Bob.'
        self.assertEqual(self.statuses(e, 'fs-BOB HELP fs-ALICE')['roles'], 'UNKNOWN')
        s = self.statuses(e, 'AGENT:fs-BOB HELP PATIENT:fs-ALICE POS:HELP')
        self.assertEqual(s['roles'], 'MISMATCH')
        self.assertEqual(s['entities'], 'MATCH')

    def test_missing_and_unrecognized_evidence(self):
        for gloss in ('', 'IX-1p GIVE:i/j (2h)BOOK', 'fs-ALICE BUY 3 UNKNOWN-LABEL'):
            self.assertEqual(self.statuses('Alice buys 3 apples.', gloss)['numbers'], 'UNKNOWN')

    def test_preserve_tokens_and_repetitions(self):
        ir = extract_gloss('fs-A-L-I-C-E BUY 3 APPLE APPLE GIVE:i/j')
        self.assertEqual(ir['tokens'], ['fs-A-L-I-C-E', 'BUY', '3', 'APPLE', 'APPLE', 'GIVE:i/j'])
        s = self.statuses('Alice buys apples.', 'fs-ALICE BUY APPLE APPLE')
        self.assertEqual(s['entities'], 'UNKNOWN')
        self.assertEqual(extract_gloss('fs-ALICE BUY APPLE APPLE')['facts']['entities']['value'], ['NAME:ALICE', 'APPLE', 'APPLE'])

    def test_partial_entity_or_count_inventory_is_unknown(self):
        self.assertEqual(self.statuses('Alice buys two apples.', 'BUY TWO APPLE')['entities'], 'UNKNOWN')
        self.assertEqual(self.statuses('Alice buys two apples and three books.', 'fs-ALICE BUY TWO APPLE BOOK')['numbers'], 'UNKNOWN')

    def test_pronouns_are_not_proper_names(self):
        ir = extract_english('She buys apples.')
        self.assertEqual(ir['facts']['entities']['value'], ['APPLE'])
        self.assertEqual(ir['facts']['roles']['state'], 'UNKNOWN')

    def test_counts_need_same_entity_alignment(self):
        statuses = self.statuses('Alice buys two apples.', 'fs-ALICE BUY TWO BOOK')
        self.assertEqual(statuses['entities'], 'MISMATCH')
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
