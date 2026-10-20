"""Coverage and paired audits; semantic accuracy requires independent human labels."""
from collections import Counter


STATUSES = {"MATCH", "MISMATCH", "UNKNOWN"}


def _source(row):
    if "source" in row:
        source = row["source"]
    else:
        source = {side: row[side]["text"] for side in ("english", "gloss")}
    if not isinstance(source, dict) or any(not isinstance(source.get(s), str)
                                           for s in ("english", "gloss")):
        raise ValueError("record requires original English/gloss source strings")
    return {s: source[s] for s in ("english", "gloss")}


def _index(rows):
    result = {}
    for row in rows:
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("record requires a nonempty ID")
        if row["id"] in result:
            raise ValueError("duplicate record ID")
        _source(row)
        result[row["id"]] = row
    return result


def _checks(row, legacy_baseline=False):
    checks = row.get("checks", [])
    if isinstance(checks, dict):  # Legacy baseline reports.
        checks = [{"field": k, **v} for k, v in checks.items()]
    allowed = STATUSES | {"MISSING"} if legacy_baseline else STATUSES
    if not isinstance(checks, list) or any(c.get("status") not in allowed for c in checks):
        raise ValueError("invalid check statuses")
    if row.get("state", "ok") not in ("ok", "error"):
        raise ValueError("invalid row state")
    if row.get("state") == "error" and checks:
        raise ValueError("error records cannot contain assessed checks")
    return checks


def _key(check):
    return tuple(check.get(k) for k in ("english_event", "gloss_event", "field", "item"))


def _summary(rows, legacy_baseline=False):
    states, reasons, fields = Counter(), Counter(), {}
    errors = any_assessed = all_unknown = 0
    for row in rows:
        checks = _checks(row, legacy_baseline=legacy_baseline)
        if row.get("state") == "error":
            errors += 1
            reasons["error:" + row.get("error", {}).get("code", "unspecified")] += 1
        elif any(c["status"] != "UNKNOWN" for c in checks):
            any_assessed += 1
        else:
            all_unknown += 1
        for c in checks:
            states[c["status"]] += 1
            reasons[c.get("reason", "unspecified")] += 1
            fields.setdefault(c["field"], Counter())[c["status"]] += 1
    n = len(rows)
    return {"n_pairs": n, "error_pairs": errors, "all_unknown_pairs": all_unknown,
            "any_assessed_pairs": any_assessed,
            "any_assessed_pair_fraction": any_assessed / n if n else None,
            "check_counts": dict(states), "reason_counts": dict(reasons),
            "per_field": {k: dict(v) for k, v in fields.items()},
            "interpretation": "Coverage of extracted facts only; no accuracy claim without independent labels."}


def audit(records, baseline=None, labels=None):
    index = _index(records)
    result = _summary(list(index.values()))
    if baseline is not None:
        old = _index(baseline)
        if old.keys() != index.keys() or any(_source(old[k]) != _source(index[k]) for k in index):
            raise ValueError("paired reports require identical IDs and original texts")
        transitions = Counter()
        for key in index:
            def state(row, legacy_baseline=False):
                if row.get("state") == "error":
                    return "error"
                return "assessed" if any(c["status"] != "UNKNOWN" for c in
                                         _checks(row, legacy_baseline=legacy_baseline)) else "all_unknown"
            transitions[f"{state(old[key], legacy_baseline=True)}->{state(index[key])}"] += 1
        result["baseline"] = _summary(list(old.values()), legacy_baseline=True)
        result["paired_transitions"] = dict(transitions)
        result["comparison_limit"] = ("Per-check denominators differ between legacy and event engines. "
                                      "MISSING is retained as assessed legacy baseline coverage only.")
    if labels is not None:
        seen, totals = set(), Counter()
        labeled_pairs = set()
        for row in labels:
            if row.get("id") not in index:
                raise ValueError("human labels reference an unknown pair")
            if row["id"] in labeled_pairs:
                raise ValueError("duplicate human label pair ID")
            labeled_pairs.add(row["id"])
            if (row.get("annotation_source") != "independent_human"
                    or not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip()):
                raise ValueError("labels require independent_human annotation and reviewer metadata")
            if {s: row.get(s) for s in ("english", "gloss")} != _source(index[row["id"]]):
                raise ValueError("human labels must match original pair texts")
            predicted = {}
            for c in _checks(index[row["id"]]):
                if _key(c) in predicted:
                    raise ValueError("duplicate predicted check identity")
                predicted[_key(c)] = c["status"]
            if not isinstance(row.get("checks"), list) or not row["checks"]:
                raise ValueError("human labels require a nonempty checks list")
            for label in row["checks"]:
                key = (row["id"], _key(label))
                if key in seen or label.get("status") not in STATUSES or not label.get("field"):
                    raise ValueError("invalid or duplicate human check label")
                seen.add(key)
                expected = label["status"]
                totals["human_checks"] += 1
                if expected == "UNKNOWN":
                    totals["unresolved_human_checks"] += 1
                    continue
                actual = predicted.get(_key(label), "UNKNOWN")
                totals["actionable_human_checks"] += 1
                totals["correct"] += actual == expected
                totals["abstentions_or_errors"] += actual == "UNKNOWN"
                totals["true_positive"] += expected == actual == "MISMATCH"
                totals["false_positive"] += expected == "MATCH" and actual == "MISMATCH"
                totals["gold_mismatches"] += expected == "MISMATCH"
                totals["false_negative_including_abstention"] += expected == "MISMATCH" and actual != "MISMATCH"
        def ratio(num, den):
            return num / den if den else None
        result["human_evaluation"] = {
            **dict(totals), "labeled_pairs": len(labeled_pairs),
            "mismatch_precision": ratio(totals["true_positive"],
                                        totals["true_positive"] + totals["false_positive"]),
            "mismatch_recall": ratio(totals["true_positive"], totals["gold_mismatches"]),
            "accuracy_including_abstention": ratio(totals["correct"], totals["actionable_human_checks"]),
            "label_limit": "Scores cover only labeled facts; reviewer independence is declared, not verified.",
        }
    return result
