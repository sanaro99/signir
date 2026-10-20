import copy
import tempfile
import json
import unittest
from pathlib import Path

from signir.events.schema import Graph
from signir.events.lexicon import Lexicon
from signir.events.quantities import compare_quantities


def graph(language="english"):
    text = "ALICE BUY 3 BOOK"
    span = lambda a, b: {"start": a, "end": b, "text": text[a:b]}
    return {
        "version": "2.0", "language": language, "text": text,
        "mentions": [
            {"id": "a", "label": "alice", "kind": "person", "evidence": [span(0, 5)]},
            {"id": "b", "label": "book", "kind": "thing", "evidence": [span(12, 16)]},
        ],
        "events": [{
            "id": "e", "predicate": "buy", "evidence": [span(6, 9)],
            "participants": ["a", "b"],
            "roles": [],
            "polarity": {"value": "unknown", "evidence": [], "basis": "unknown"},
            "scope": {"kind": "asserted", "evidence": [span(6, 9)]},
            "quantities": [{"mention_id": "b", "kind": "count", "unit": "item",
                            "value": "3", "relation": "eq", "evidence": [span(10, 11)]}],
        }],
        "unresolved": [],
    }


class EventSchemaTests(unittest.TestCase):
    def test_roundtrip_and_original_evidence(self):
        data = graph()
        self.assertEqual(Graph.model_validate(data).text, data["text"])
        for mutate in [
            lambda d: d["mentions"][0]["evidence"][0].update(text="BOB"),
            lambda d: d["events"][0]["participants"].append("missing"),
            lambda d: d["mentions"].append(copy.deepcopy(d["mentions"][0])),
            lambda d: d["events"][0]["scope"].update(parent_event="e"),
            lambda d: d.update(version="3.0"),
            lambda d: d["events"][0]["quantities"][0].update(value="NaN"),
            lambda d: d["events"][0]["quantities"][0].update(relation="range", upper="2"),
        ]:
            broken = copy.deepcopy(data)
            mutate(broken)
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                Graph.model_validate(broken)

    def test_gloss_does_not_infer_positive_or_roles_from_order(self):
        data = graph("gloss")
        data["events"][0]["polarity"] = {
            "value": "positive", "basis": "syntactic",
            "evidence": data["events"][0]["evidence"],
        }
        with self.assertRaises(ValueError):
            Graph.model_validate(data)
        data = graph("gloss")
        data["events"][0]["roles"] = [{
            "role": "agent", "mention_id": "a", "basis": "word_order",
            "evidence": data["mentions"][0]["evidence"],
        }]
        with self.assertRaises(ValueError):
            Graph.model_validate(data)

    def test_quantity_intervals(self):
        q = Graph.model_validate(graph()).events[0].quantities[0]
        cases = [
            ({"value": "3.0"}, "MATCH"),
            ({"value": "4"}, "MISMATCH"),
            ({"relation": "ge"}, "UNKNOWN"),
            ({"relation": "gt"}, "MISMATCH"),
            ({"relation": "approx"}, "UNKNOWN"),
            ({"unit": "dollar"}, "UNKNOWN"),
        ]
        for update, expected in cases:
            other = type(q).model_validate(q.model_dump() | update)
            self.assertEqual(compare_quantities(q, other)["status"], expected)

    def test_lexicon_retains_alternatives_and_exact_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lexicon.json"
            path.write_text(json.dumps({"version": "demo1", "entries": [
                {"label": "BANK-1", "concepts": ["bank_finance", "bank_river"],
                 "kind": "thing", "provenance": "authored test"}
            ]}))
            lexicon = Lexicon.load(path)
            self.assertEqual(len(lexicon.hints("BANK-1 BUY")[0]["concepts"]), 2)
            self.assertEqual(lexicon.hints("BANK"), [])

    def test_excessive_event_graph_is_rejected_before_assignment(self):
        data = graph()
        data["events"] = [copy.deepcopy(data["events"][0]) for _ in range(65)]
        for i, event in enumerate(data["events"]):
            event["id"] = f"e{i}"
        with self.assertRaises(ValueError):
            Graph.model_validate(data)
