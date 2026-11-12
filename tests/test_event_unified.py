"""One representation across engines: rule readers emit SignIR 2.0, which carries MISSING and confidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from signir.events.compare import compare_graphs
from signir.events.extract import extract_graph, extraction_schema
from signir.events.from_rules import english_graph, gloss_graph
from signir.events.schema import Graph
from signir.events.workflow import run_rules

ROOT = Path(__file__).resolve().parents[1]


def checks(english, gloss, nmm=None, notation=None):
    result = compare_graphs(english_graph(english), gloss_graph(gloss, nmm, notation))
    return [(c['field'], c['status'], c['confidence']) for c in result['checks']]


def field(rows, name):
    return [(s, c) for f, s, c in rows if f == name]


class RuleReaderGraphTests(unittest.TestCase):
    def test_english_graph_records_events_roles_quantities_and_evidence(self):
        g = english_graph('Alice buys 3 apples.')
        event = g.events[0]
        self.assertEqual(event.predicate, 'buy')
        self.assertEqual({(r.role, r.basis) for r in event.roles}, {('agent', 'syntactic'), ('patient', 'syntactic')})
        self.assertTrue(event.roles_complete)
        self.assertEqual((event.quantities[0].value, event.quantities[0].kind), ('3', 'count'))
        self.assertEqual(g.text[event.evidence[0].start:event.evidence[0].end], 'buys')

    def test_english_scope_markers(self):
        g = english_graph('If it rains, Alice will stay home.')
        kinds = {e.predicate: e.scope.kind for e in g.events}
        self.assertEqual(kinds['rain'], 'conditional')
        self.assertEqual(kinds['stay'], 'asserted')

    def test_gloss_graph_forms_and_nonmanual_labels(self):
        g = gloss_graph('IX-3p:i fs-BOB NOT LIKE DOG ns-GALLAUDET', {'negation': True, 'topic': False})
        forms = {m.label: m.form for m in g.mentions}
        self.assertEqual(forms['bob'], 'fingerspelled')
        self.assertEqual(forms['gallaudet'], 'name')
        self.assertEqual(forms['ix-3p:i'], 'pointing')
        self.assertEqual(g.marker('negation'), True)
        self.assertEqual(g.events[0].polarity.value, 'negative')

    def test_gloss_reader_never_receives_english(self):
        # The gloss reader's signature has no English argument; same gloss, same graph.
        self.assertEqual(gloss_graph('fs-BOB LIKE DOG').model_dump(), gloss_graph('fs-BOB LIKE DOG').model_dump())


class MissingAndConfidenceTests(unittest.TestCase):
    def test_changed_number_is_high_mismatch(self):
        self.assertIn(('MISMATCH', 'high'), field(checks('Alice buys 3 apples.', 'fs-ALICE BUY 9 APPLE'), 'numbers'))

    def test_dropped_number_is_missing(self):
        self.assertIn(('MISSING', 'high'), field(checks('Alice buys 3 apples.', 'fs-ALICE BUY APPLE'), 'numbers'))

    def test_negation_missing_only_when_nonmanual_is_annotated_absent(self):
        self.assertIn(('MISSING', 'high'), field(checks('Bob does not like dogs.', 'fs-BOB LIKE DOG',
                                                        {'negation': False}), 'negation'))
        self.assertIn(('UNKNOWN', None), field(checks('Bob does not like dogs.', 'fs-BOB LIKE DOG'), 'negation'))
        self.assertIn(('MATCH', None), field(checks('Bob does not like dogs.', 'fs-BOB LIKE DOG',
                                                    {'negation': True}), 'negation'))

    def test_head_shake_on_positive_sentence_is_low(self):
        self.assertIn(('MISMATCH', 'low'), field(checks('Bob likes dogs.', 'fs-BOB LIKE DOG',
                                                        {'negation': True}), 'negation'))

    def test_word_order_roles_follow_the_shared_policy(self):
        english = 'The teacher helps the student.'
        self.assertIn(('MISMATCH', 'low'), field(checks(english, 'STUDENT HELP TEACHER'), 'roles'))
        self.assertIn(('UNKNOWN', None), field(checks(english, 'STUDENT HELP TEACHER', {'topic': True}), 'roles'))

    def test_participant_absent_from_gloss_is_missing_but_synonym_is_not(self):
        self.assertIn(('MISSING', 'high'), field(checks('Alice buys 3 apples.', 'fs-ALICE BUY 3 BOOK'), 'entities'))
        rows = checks('The kids play sports.', 'CHILDREN PLAY COMPETITION')
        self.assertFalse(any(s == 'MISSING' for _, s, _ in rows))

    def test_unmatched_asserted_event_is_missing(self):
        self.assertIn(('MISSING', 'high'), field(checks('The teacher reads a book.', 'TEACHER'), 'alignment'))
        self.assertIn(('MISMATCH', 'high'), field(checks('The teacher buys a book.', 'TEACHER SELL BOOK'),
                                                  'predicate'))

    def test_match_and_unknown_have_no_confidence(self):
        rows = checks('Alice buys 3 apples.', 'fs-ALICE BUY 3 APPLE')
        self.assertTrue(all(c is None for _, s, c in rows if s in ('MATCH', 'UNKNOWN')))


class ModelReaderNonmanualTests(unittest.TestCase):
    class Client:
        def __init__(self):
            self.traces, self.messages = [], None

        def extract(self, messages, schema):
            self.messages = messages
            self.traces.append({})
            return {"mentions": [], "events": [], "unresolved": []}

    def test_gloss_reader_receives_its_own_nonmanual_labels_and_graph_keeps_them(self):
        client = self.Client()
        g = extract_graph('BOB LIKE DOG', 'gloss', client, nonmanual={'negation': False, 'other': True})
        sent = json.loads(client.messages[1]['content'])
        self.assertEqual(sent['nonmanual'], [{'label': 'negation', 'value': False}])
        self.assertEqual(g.marker('negation'), False)
        self.assertNotIn('nonmanual', extraction_schema()['properties'])
        with self.assertRaises(ValueError):
            extract_graph('Bob likes dogs.', 'english', self.Client(), nonmanual={'negation': True})


class RulesWorkflowAndSchemaFileTests(unittest.TestCase):
    def test_rules_engine_batch_bundle(self):
        rows = [{'id': 'a', 'english': 'Bob does not like dogs.', 'gloss': 'fs-BOB LIKE DOG',
                 'gloss_nmm': {'negation': False}, 'source_group': 'a', 'provenance': {'kind': 'test', 'version': '1'}}]
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_rules(rows, Path(tmp) / 'out')
            self.assertEqual(summary['check_counts'].get('MISSING'), 1)
            manifest = json.loads((Path(tmp) / 'out' / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['model_execution'], 'rule_readers')
            self.assertIn('confidence', (Path(tmp) / 'out' / 'checks.csv').read_text(encoding='utf-8').splitlines()[0])

    def test_published_json_schema_matches_models(self):
        spec = importlib.util.spec_from_file_location('export_schema', ROOT / 'scripts' / 'export_schema.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual((ROOT / 'schemas' / 'signir-2.0.schema.json').read_text(encoding='utf-8'),
                         module.schema_text(), 'Run python scripts/export_schema.py')
        self.assertIn('nonmanual', Graph.model_json_schema()['properties'])


if __name__ == '__main__':
    unittest.main()
