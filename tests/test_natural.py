import unittest
from signir.compare import check_pair
from signir.schema import validate

class NaturalExtractionTests(unittest.TestCase):
    # These catch all-or-nothing grammar rejection, evidence loss, and false scope.
    def test_articles_and_unrestricted_noun(self):
        r = check_pair('The teacher explains the lesson.', 'TEACHER EXPLAIN LESSON')
        self.assertEqual(r['checks']['action']['status'], 'MATCH')
        self.assertEqual(r['checks']['entities']['status'], 'MATCH')
        self.assertEqual(r['checks']['roles']['status'], 'UNKNOWN')

    def test_noun_verb_homograph_does_not_create_action_alarm(self):
        r = check_pair('That watch costs three thousand dollars.', 'THAT WATCH COST 3000 DOLLAR')
        self.assertEqual(r['checks']['action']['status'], 'UNKNOWN')

    def test_explicit_negative_have_survives_auxiliary_lexicon(self):
        r = check_pair('I will not have an umbrella.', 'IX-1p NOT HAVE UMBRELLA')
        self.assertEqual(r['checks']['negation']['status'], 'MATCH')

    def test_unknown_english_spelling_is_not_an_action_error(self):
        r = check_pair('My cousin never vists me.', 'POSS-1p COUSIN NEVER VISIT IX-1p')
        self.assertEqual(r['checks']['action']['status'], 'UNKNOWN')

    def test_polarity_marker_scopes_one_occurrence_of_repeated_verb(self):
        e = 'He does not want anything, but I think he wants something.'
        r = check_pair(e, 'IX-3p POS:WANT WANT ANYTHING IX-1p THINK IX-3p WANT SOMETHING')
        self.assertEqual(r['checks']['negation']['status'], 'MISMATCH')

    def test_money_is_not_a_count_of_gift_cards(self):
        r = check_pair('He will get a $100 gift card.', 'IX-3p GET 100 DOLLAR GIFT CARD')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')
        self.assertEqual(r['checks']['numbers']['english_value'], [{'entity': 'DOLLAR', 'count': 100}])

    def test_compound_number_is_one_quantity(self):
        r = check_pair('That watch costs three thousand dollars.', 'THAT WATCH COST 3000 DOLLAR')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')

    def test_postposed_chapter_number(self):
        r = check_pair('Please read chapter two.', 'PLEASE READ CHAPTER 2')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')

    def test_age_number_does_not_attach_to_following_time(self):
        r = check_pair('He was 15 years old at that time.', 'IX-3p AGE 15 TIME THAT')
        self.assertEqual(r['checks']['numbers']['status'], 'UNKNOWN')
        self.assertEqual(r['checks']['numbers']['gloss_value'], [{'entity': 'AGE', 'count': 15}])
        r = check_pair('The teacher visits the museum.', 'TEACHER VISIT MUSEUM')
        self.assertEqual(r['checks']['action']['status'], 'UNKNOWN')

    def test_unfamiliar_label_does_not_erase_number(self):
        r = check_pair('The teacher bought three apples in the morning.', 'TEACHER BUY THREE APPLE UNMAPPED-LABEL')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')
        changed = check_pair('The teacher bought three apples in the morning.', 'TEACHER BUY NINE APPLE UNMAPPED-LABEL')
        self.assertEqual(changed['checks']['numbers']['status'], 'MISMATCH')

    def test_spelled_common_noun_is_not_a_person(self):
        r = check_pair('The discussion shows two different orientations.', 'DISCUSSION SHOW TWO DIFFERENT fs-O-R-I-E-N-T-A-T-I-O-N')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')
        self.assertEqual(r['checks']['numbers']['gloss_value'], [{'entity': 'ORIENTATION', 'count': 2}])

    def test_local_negation_in_multiple_clauses(self):
        r = check_pair('The workers made progress, but it was not permitted.', 'WORKER PROGRESS BUT NOT PERMIT')
        self.assertEqual(r['checks']['negation']['status'], 'MATCH')
        self.assertEqual(r['checks']['negation']['english_value'], {'action': 'PERMIT', 'negative': True})

    def test_count_scope_is_not_taken_from_english(self):
        r = check_pair('The teacher bought three apples.', 'TEACHER BUY THREE BOOK UNMAPPED')
        self.assertEqual(r['checks']['numbers']['status'], 'UNKNOWN')

    def test_multiple_actions_not_silently_reduced_to_first(self):
        r = check_pair('The teacher visits the museum and helps the student.', 'TEACHER VISIT MUSEUM HELP STUDENT')
        self.assertEqual(r['checks']['action']['status'], 'UNKNOWN')

    def test_natural_evidence_offsets_validate(self):
        r = check_pair('The teachers bought two books yesterday.', '(2h)TEACHER BUY TWO BOOK UNKNOWN-LABEL')
        self.assertEqual(r['checks']['numbers']['status'], 'MATCH')
        validate(r['english']); validate(r['gloss'])

if __name__ == '__main__':
    unittest.main()
