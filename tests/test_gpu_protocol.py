import copy
import json
from pathlib import Path
import tempfile
import unittest

from signir.schema import fact, record


class GPUProtocolTests(unittest.TestCase):
    def api(self):
        from signir.gpu import protocol
        return protocol

    def test_gloss_request_never_contains_source_or_gold(self):
        pair = {'id': 'x', 'english': 'SOURCE SECRET', 'gloss': 'APPLE',
                'gold': 'GOLD SECRET', 'reference_gloss': 'REFERENCE SECRET'}
        request = self.api().make_request('gloss', pair)
        user = json.loads(request['messages'][1]['content'])
        self.assertEqual(user, {'language': 'gloss', 'text': 'APPLE'})
        self.assertNotIn('SOURCE SECRET', json.dumps(request))
        self.assertNotIn('GOLD SECRET', json.dumps(request))
        self.assertNotIn('REFERENCE SECRET', json.dumps(request))

    def test_english_request_never_contains_gloss(self):
        request = self.api().make_request('english', {'english': 'Apple.', 'gloss': 'TARGET SECRET'})
        self.assertNotIn('TARGET SECRET', json.dumps(request))

    def test_extraction_preserves_original_unicode_offsets(self):
        text = 'Éva buys apples.'
        payload = {'facts': record(text, 'english', 'authored')['facts']}
        payload['facts']['action'] = fact('BUY', [{'start': 4, 'end': 8, 'text': 'buys'}])
        result = self.api().parse_extraction(payload, text, 'english')
        self.assertEqual(result['text'], text)
        self.assertEqual(result['facts']['action']['value'], 'BUY')
        payload['facts']['action']['evidence'][0]['start'] = 5
        with self.assertRaises(ValueError):
            self.api().parse_extraction(payload, text, 'english')

    def test_invalid_nested_values_and_boolean_offsets_rejected(self):
        text = 'BUY'
        original = {'facts': record(text, 'english', 'authored')['facts']}
        evidence = [{'start': 0, 'end': 3, 'text': 'BUY'}]
        invalid = [('roles', {'action': None, 'agent': [], 'patient': None}),
                   ('negation', {'action': [], 'negative': True}),
                   ('numbers', [{'entity': None, 'count': 3}]),
                   ('numbers', [{'entity': 'APPLE', 'count': True}])]
        for name, value in invalid:
            payload = copy.deepcopy(original)
            payload['facts'][name] = fact(value, evidence)
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                self.api().parse_extraction(payload, text, 'english')
        payload = copy.deepcopy(original)
        payload['facts']['action'] = fact('BUY', [{'start': False, 'end': 3, 'text': 'BUY'}])
        with self.assertRaises(ValueError):
            self.api().parse_extraction(payload, text, 'english')

    def test_gloss_roles_and_unmarked_positive_polarity_rejected(self):
        for name, value in [('roles', {'action': 'BUY', 'agent': 'ALICE', 'patient': 'APPLE'}),
                            ('negation', {'action': 'BUY', 'negative': False})]:
            payload = {'facts': record('BUY', 'gloss', 'authored')['facts']}
            payload['facts'][name] = fact(value, [{'start': 0, 'end': 3, 'text': 'BUY'}])
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.api().parse_extraction(payload, 'BUY', 'gloss')

    def test_unknown_cannot_hide_a_value(self):
        payload = {'facts': record('BUY', 'gloss', 'authored')['facts']}
        payload['facts']['action']['value'] = 'BUY'
        with self.assertRaises(ValueError):
            self.api().parse_extraction(payload, 'BUY', 'gloss')

    def test_repeated_number_entities_and_property_conflicts_abstain(self):
        a = record('BOOK BOOK', 'english', 'authored')
        b = record('BOOK BOOK', 'gloss', 'authored')
        evidence = [{'start': 0, 'end': 4, 'text': 'BOOK'}]
        a['facts']['numbers'] = fact([{'entity': 'BOOK', 'count': 3}, {'entity': 'BOOK', 'count': 5}], evidence)
        b['facts']['numbers'] = fact([{'entity': 'BOOK', 'count': 5}, {'entity': 'BOOK', 'count': 3}], evidence)
        a['facts']['action'] = fact('PROPERTY:CLEAN', evidence)
        b['facts']['action'] = fact('CLEAN', evidence)
        checks = self.api().compare_records(a, b)
        self.assertEqual(checks['numbers']['status'], 'UNKNOWN')
        self.assertEqual(checks['action']['status'], 'UNKNOWN')

    def test_judge_requires_both_evidence_sides_for_assessed_check(self):
        checks = {name: {'status': 'UNKNOWN', 'reason': 'insufficient',
                        'english_evidence': [], 'gloss_evidence': []}
                  for name in ('entities', 'action', 'negation', 'numbers', 'roles')}
        checks['action']['status'] = 'MATCH'
        with self.assertRaises(ValueError):
            self.api().parse_judge({'checks': checks}, 'buy', 'BUY')

    def test_input_duplicates_and_document_leakage_rejected(self):
        from signir.gpu.storage import load_pairs
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.jsonl'
            a = {'id': 'a', 'english': 'a', 'gloss': 'A', 'source_group': 'doc', 'split': 'dev'}
            b = {**a, 'id': 'b', 'english': 'b', 'split': 'test'}
            for rows in ([a, a], [a, b], [a, {**b, 'source_group': 'other', 'english': 'a'}]):
                path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    load_pairs(path)

    def test_freeze_rejects_changed_input_and_unsafe_model_revision(self):
        from signir.gpu.storage import freeze_experiment, verify_freeze
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.jsonl'
            path.write_text('{"id":"a","english":"a","gloss":"A","source_group":"doc"}\n', encoding='utf-8')
            config = self.api().default_config()
            with self.assertRaises(ValueError):
                freeze_experiment(path, config, 'main', 'replay')
            frozen = freeze_experiment(path, config, 'a' * 40, 'replay')
            verify_freeze(path, frozen)
            path.write_text(path.read_text(encoding='utf-8').replace('"A"', '"B"'), encoding='utf-8')
            with self.assertRaises(ValueError):
                verify_freeze(path, frozen)


if __name__ == '__main__':
    unittest.main()
