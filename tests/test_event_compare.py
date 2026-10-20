import copy
import unittest

from test_event_schema import graph
from signir.events.schema import Graph
from signir.events.compare import compare_graphs


def multi(language="english", identical=False):
    a, b = graph(language), graph(language)
    if not identical:
        b["text"] = b["text"].replace("ALICE", "BOBBY")
        b["mentions"][0].update(label="bobby")
        b["mentions"][0]["evidence"][0]["text"] = "BOBBY"
    offset = len(a["text"]) + 1

    def shift(obj):
        if isinstance(obj, list):
            for x in obj:
                shift(x)
        if isinstance(obj, dict):
            if set(obj) == {"start", "end", "text"}:
                obj["start"] += offset
                obj["end"] += offset
            else:
                for v in obj.values():
                    shift(v)
    shift(b["mentions"])
    shift(b["events"])
    for m in b["mentions"]:
        m["id"] += "2"
    for e in b["events"]:
        e["id"] += "2"
        e["participants"] = [x + "2" for x in e["participants"]]
        for q in e["quantities"]:
            q["mention_id"] += "2"
    a["text"] += "\n" + b["text"]
    a["mentions"] += b["mentions"]
    a["events"] += b["events"]
    return a


def check(a, b):
    return compare_graphs(Graph.model_validate(a), Graph.model_validate(b))


class EventCompareTests(unittest.TestCase):
    def test_reordered_events_and_swapped_counts_cannot_match_away_errors(self):
        a, b = multi(), multi("gloss")
        a["events"][1]["quantities"][0]["value"] = "5"
        b["events"][0]["quantities"][0]["value"] = "5"
        b["events"].reverse()
        result = check(a, b)
        counts = [c for c in result["checks"] if c["field"] == "numbers"]
        self.assertEqual([c["status"] for c in counts], ["MISMATCH", "MISMATCH"])
        self.assertEqual(result["alignment"]["pairs"], [["e", "e"], ["e2", "e2"]])

    def test_identical_events_are_ambiguous_despite_counts_and_order(self):
        a, b = multi(identical=True), multi("gloss", identical=True)
        b["events"][1]["quantities"][0]["value"] = "7"
        result = check(a, b)
        self.assertEqual(result["alignment"]["pairs"], [])
        self.assertTrue(all(c["status"] == "UNKNOWN" for c in result["checks"]))

    def test_unmatched_event_does_not_erase_independent_assessment(self):
        result = check(multi(), graph("gloss"))
        self.assertEqual(result["alignment"]["pairs"], [["e", "e"]])
        self.assertTrue(any(c["status"] == "MATCH" for c in result["checks"]))
        self.assertTrue(any(c["reason"] == "unmatched_event" for c in result["checks"]))

    def test_role_reversal(self):
        a, b = graph(), graph("gloss")
        for data, reversed_roles in [(a, False), (b, True)]:
            data["events"][0]["roles_complete"] = True
            data["events"][0]["roles"] = [
                {"role": role, "mention_id": mention, "basis": "explicit_annotation",
                 "evidence": data["mentions"][0]["evidence"]}
                for role, mention in zip(["agent", "patient"], ["b", "a"] if reversed_roles else ["a", "b"])
            ]
        roles = [c for c in check(a, b)["checks"] if c["field"] == "roles"]
        self.assertEqual(roles[0]["status"], "MISMATCH")

    def test_partial_role_membership_is_not_a_conflict(self):
        a, b = graph(), graph("gloss")
        for data, members in [(a, ["a", "b"]), (b, ["a"])]:
            data["events"][0]["roles"] = [
                {"role": "agent", "mention_id": mid, "basis": "explicit_annotation",
                 "evidence": data["mentions"][0]["evidence"]} for mid in members
            ]
        roles = [c for c in check(a, b)["checks"] if c["field"] == "roles"]
        self.assertEqual(roles[0]["status"], "UNKNOWN")

    def test_scope_and_lexical_ambiguity_abstain(self):
        for change in ["scope", "alternatives"]:
            a, b = graph(), graph("gloss")
            if change == "scope":
                b["events"][0]["scope"]["kind"] = "conditional"
            else:
                b["events"][0]["alternatives"] = ["borrow"]
            result = check(a, b)
            count = next(c for c in result["checks"] if c["field"] == "numbers")
            self.assertEqual(count["status"], "UNKNOWN")

    def test_empty_graph_is_not_a_vacuous_match(self):
        a, b = graph(), graph("gloss")
        a["events"], b["events"] = [], []
        result = check(a, b)
        self.assertEqual(result["checks"][0]["status"], "UNKNOWN")

    def test_repeated_mentions_not_matched_by_quantity(self):
        a, b = graph(), graph("gloss")
        for data in [a, b]:
            m = copy.deepcopy(data["mentions"][1])
            m["id"] = "c"
            data["mentions"].append(m)
            data["events"][0]["participants"].append("c")
        numbers = [c for c in check(a, b)["checks"] if c["field"] == "numbers"]
        self.assertTrue(all(c["status"] == "UNKNOWN" for c in numbers))
