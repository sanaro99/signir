"""Meaning-preserving translation choices that used to raise false alarms, and real errors that must not."""
import unittest

from signir import lexicon
from signir.compare import check_pair


def statuses(english, gloss, nmm=None, notation=None):
    return {k: (v['status'], v['confidence']) for k, v in check_pair(english, gloss, nmm, notation)['checks'].items()}


class BuiltinLexiconTests(unittest.TestCase):
    def setUp(self):
        lexicon.configure()

    def test_common_correspondences_are_recognized(self):
        self.assertEqual(statuses('The kids play sports.', 'CHILDREN PLAY COMPETITION')['entities'][0], 'MATCH')
        self.assertEqual(statuses('I watched a movie.', 'IX-1p LOOK MOVIE')['action'][0], 'MATCH')

    def test_disabling_lexicons_restores_the_literal_reader(self):
        lexicon.configure([])
        try:
            self.assertEqual(statuses('The kids play sports.', 'CHILDREN PLAY COMPETITION')['entities'][0], 'MISSING')
        finally:
            lexicon.configure()

    def test_infinitive_sign_bank_keys_and_compound_labels(self):
        self.assertEqual(lexicon._english_key('to love'), 'love')
        self.assertIsNone(lexicon._english_key('look at'))
        self.assertEqual(lexicon.label_core('ONE* (ONE+HUNDRED)'), 'ONE')


class FalseAlarmTests(unittest.TestCase):
    def setUp(self):
        lexicon.configure([])

    def tearDown(self):
        lexicon.configure()

    def test_word_family_counts_as_expressed(self):
        self.assertEqual(statuses('We saw a big improvement.', 'IX-1p SEE BIG IMPROVE')['entities'][0], 'MATCH')
        self.assertEqual(statuses('The artist paints.', 'ART PAINT')['entities'][0], 'MATCH')

    def test_fillers_are_not_entities(self):
        self.assertNotEqual(statuses('So I feel like... umm...', 'FEEL SAME 5"umm"')['entities'][0], 'MISSING')

    def test_name_inside_slash_alternative(self):
        self.assertEqual(statuses('I am going to Hawaii.', 'IX-1p GO-OUT HANDSOME/ns-HAWAII_2+')['entities'][0], 'MATCH')

    def test_partial_fingerspelling(self):
        self.assertEqual(statuses('The buffalo is blue.', 'fs-B-U-F-F BLUE')['entities'][0], 'MATCH')

    def test_negative_meaning_sign_can_carry_negation(self):
        result = statuses("I don't like bicycles.", 'IX-1p VOMIT/HATE BICYCLE', {'negation': False})
        self.assertEqual(result['negation'][0], 'UNKNOWN')
        self.assertEqual(result['action'][0], 'UNKNOWN')

    def test_head_shake_alone_on_positive_sentence_is_low_confidence(self):
        self.assertEqual(statuses('Bob likes dogs.', 'fs-BOB LIKE DOG', {'negation': True})['negation'],
                         ('MISMATCH', 'low'))

    def test_word_order_role_reversal_is_low_confidence_outside_english_order_gloss(self):
        self.assertEqual(statuses('Alice helps Bob.', 'fs-BOB HELP fs-ALICE')['roles'], ('MISMATCH', 'low'))
        self.assertEqual(statuses('The teacher helps the student.', 'STUDENT HELP TEACHER', notation='aslg_pc12')['roles'],
                         ('MISMATCH', 'high'))


class RealErrorTests(unittest.TestCase):
    """Errors the fixes must keep flagging with high confidence."""

    def setUp(self):
        lexicon.configure()

    def test_swapped_core_noun(self):
        self.assertEqual(statuses('Bob helps his mother.', 'fs-BOB HELP FATHER')['entities'], ('MISSING', 'high'))

    def test_swapped_name(self):
        self.assertEqual(statuses('Alice visits Bob.', 'fs-ALICE VISIT fs-ZOE')['entities'], ('MISSING', 'high'))

    def test_changed_number(self):
        self.assertEqual(statuses('Alice buys 3 apples.', 'fs-ALICE BUY 9 APPLE')['numbers'], ('MISMATCH', 'high'))

    def test_dropped_negation_with_nmm(self):
        self.assertEqual(statuses('Bob does not like dogs.', 'fs-BOB LIKE DOG', {'negation': False})['negation'],
                         ('MISSING', 'high'))

    def test_added_negation_sign(self):
        self.assertEqual(statuses('Bob likes dogs.', 'fs-BOB NOT LIKE DOG', {'negation': False})['negation'],
                         ('MISMATCH', 'high'))

    def test_abstract_or_peripheral_omission_is_flagged_but_low(self):
        status, confidence = statuses('Alice explained the situation in detail.', 'fs-ALICE EXPLAIN')['entities']
        self.assertEqual((status, confidence), ('MISSING', 'low'))

    def test_match_and_unknown_carry_no_confidence(self):
        checks = check_pair('Alice buys 3 apples.', 'fs-ALICE BUY 3 APPLE')['checks']
        self.assertTrue(all(c['confidence'] is None for c in checks.values() if c['status'] in ('MATCH', 'UNKNOWN')))


if __name__ == '__main__':
    unittest.main()
