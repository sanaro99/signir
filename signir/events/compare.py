"""Per-event comparisons. A MATCH applies only to its explicitly assessed fact."""
from collections import Counter

from .alignment import align_events
from .quantities import compare_quantities
from .schema import Graph


def compare_graphs(english: Graph, gloss: Graph) -> dict:
    if english.language != "english" or gloss.language != "gloss":
        raise ValueError("comparison requires English then gloss")
    alignment = align_events(english, gloss)
    checks = []
    em, gm = ({m.id: m for m in g.mentions} for g in (english, gloss))
    ee, ge = ({e.id: e for e in g.events} for g in (english, gloss))

    def add(field, status, reason, x=None, y=None, left=None, right=None, item=None,
            left_evidence=None, right_evidence=None):
        checks.append({
            "english_event": x.id if x else None, "gloss_event": y.id if y else None,
            "field": field, "item": item, "status": status, "reason": reason,
            "english_value": left, "gloss_value": right,
            "evidence": {
                "english": [s.model_dump() for s in (left_evidence if left_evidence is not None
                                                   else x.evidence if x else [])],
                "gloss": [s.model_dump() for s in (right_evidence if right_evidence is not None
                                                 else y.evidence if y else [])],
            },
            "assessment_scope": "extracted_event_fact_only",
        })

    for eid, gid in alignment["pairs"]:
        x, y = ee[eid], ge[gid]
        same = x.predicate.casefold() == y.predicate.casefold()
        ambiguous = bool(x.alternatives or y.alternatives)
        add("predicate", "UNKNOWN" if ambiguous else "MATCH" if same else "MISMATCH",
            "lexical_ambiguity" if ambiguous else "predicate_labels", x, y, x.predicate, y.predicate)
        # Nonasserted contexts need operator/condition identity beyond a coarse label.
        # Keep them visible until that identity is represented and validated.
        scope_ok = (x.scope.kind == y.scope.kind == "asserted"
                    and x.scope.parent_event is None and y.scope.parent_event is None)
        add("scope", "MATCH" if scope_ok else "UNKNOWN",
            "asserted_scope" if scope_ok else "unsupported_scope", x, y,
            x.scope.model_dump(), y.scope.model_dump(),
            left_evidence=x.scope.evidence, right_evidence=y.scope.evidence)
        blocked = ("unsupported_scope" if not scope_ok else
                   "lexical_ambiguity" if ambiguous else
                   "different_predicates" if not same else None)
        left_mentions = [em[mid] for mid in x.participants]
        right_mentions = [gm[mid] for mid in y.participants]
        lc = Counter(m.label.casefold() for m in left_mentions)
        rc = Counter(m.label.casefold() for m in right_mentions)
        entity_ambiguous = any(m.alternatives for m in left_mentions + right_mentions)
        entity_same = lc == rc and bool(lc) and not entity_ambiguous
        add("entities", "MATCH" if entity_same else "UNKNOWN",
            "equal_participant_labels" if entity_same else "participant_alignment_incomplete",
            x, y, dict(lc), dict(rc),
            left_evidence=[s for m in left_mentions for s in m.evidence],
            right_evidence=[s for m in right_mentions for s in m.evidence])
        unique = {
            label: (next(m for m in left_mentions if m.label.casefold() == label),
                    next(m for m in right_mentions if m.label.casefold() == label))
            for label in lc.keys() & rc.keys()
            if lc[label] == rc[label] == 1
            and not next(m for m in left_mentions if m.label.casefold() == label).alternatives
            and not next(m for m in right_mentions if m.label.casefold() == label).alternatives
        }
        role_maps = []
        for event, mentions in [(x, em), (y, gm)]:
            role_maps.append({role: sorted(mentions[r.mention_id].label.casefold()
                                          for r in event.roles if r.role == role)
                              for role in {r.role for r in event.roles}})
        lr, rr = role_maps
        shared_roles = lr.keys() & rr.keys()
        roles_resolved = bool(shared_roles) and all(
            label in unique for role in shared_roles for label in lr[role] + rr[role])
        if blocked or not roles_resolved:
            add("roles", "UNKNOWN", blocked or "role_evidence_incomplete", x, y, lr, rr)
        else:
            equal = lr == rr
            complete = x.roles_complete and y.roles_complete
            add("roles", "MATCH" if equal else "MISMATCH" if complete else "UNKNOWN",
                "equal_observed_role_assignments" if equal else
                "complete_role_assignment_conflict" if complete else "role_evidence_incomplete",
                x, y, lr, rr,
                left_evidence=[s for r in x.roles for s in r.evidence],
                right_evidence=[s for r in y.roles for s in r.evidence])
        xp, yp = x.polarity.value, y.polarity.value
        add("negation", "UNKNOWN" if blocked or "unknown" in (xp, yp)
            else "MATCH" if xp == yp else "MISMATCH",
            blocked or ("polarity_unresolved" if "unknown" in (xp, yp) else "polarity_values"),
            x, y, xp, yp, left_evidence=x.polarity.evidence, right_evidence=y.polarity.evidence)

        consumed_x, consumed_y = set(), set()
        for label, (lm, rm) in sorted(unique.items()):
            aq = [(i, q) for i, q in enumerate(x.quantities) if q.mention_id == lm.id]
            bq = [(i, q) for i, q in enumerate(y.quantities) if q.mention_id == rm.id]
            keys = {(q.kind, q.unit) for _, q in aq + bq}
            for kind, unit in sorted(keys):
                aa = [(i, q) for i, q in aq if (q.kind, q.unit) == (kind, unit)]
                bb = [(i, q) for i, q in bq if (q.kind, q.unit) == (kind, unit)]
                if len(aa) != 1 or len(bb) != 1:
                    continue
                (ai, av), (bi, bv) = aa[0], bb[0]
                consumed_x.add(ai)
                consumed_y.add(bi)
                result = ({"status": "UNKNOWN", "reason": blocked} if blocked
                          else compare_quantities(av, bv))
                add("numbers", **result, x=x, y=y, left=av.model_dump(), right=bv.model_dump(),
                    item=f"{label}:{kind}:{unit}",
                    left_evidence=av.evidence, right_evidence=bv.evidence)
        if (not x.quantities and not y.quantities or len(consumed_x) < len(x.quantities)
                or len(consumed_y) < len(y.quantities)):
            add("numbers", "UNKNOWN", blocked or "quantity_alignment_incomplete", x, y,
                [q.model_dump() for i, q in enumerate(x.quantities) if i not in consumed_x],
                [q.model_dump() for i, q in enumerate(y.quantities) if i not in consumed_y],
                item="unresolved")

    ambiguous_a = {p[0] for p in alignment["ambiguous_candidates"]}
    ambiguous_b = {p[1] for p in alignment["ambiguous_candidates"]}
    for side, ids, events, ambiguous_ids in [
        ("english", alignment["unmatched_english"], ee, ambiguous_a),
        ("gloss", alignment["unmatched_gloss"], ge, ambiguous_b),
    ]:
        for eid in ids:
            add("alignment", "UNKNOWN", "ambiguous_event_alignment" if eid in ambiguous_ids
                else "unmatched_event", x=events[eid] if side == "english" else None,
                y=events[eid] if side == "gloss" else None)
    for graph in (english, gloss):
        for i, unresolved in enumerate(graph.unresolved):
            add("extraction", "UNKNOWN", unresolved.reason, item=f"{graph.language}:{i}",
                left=unresolved.detail if graph.language == "english" else None,
                right=unresolved.detail if graph.language == "gloss" else None,
                left_evidence=unresolved.evidence if graph.language == "english" else [],
                right_evidence=unresolved.evidence if graph.language == "gloss" else [])
    if not checks:
        add("extraction", "UNKNOWN", "no_events_extracted")
    return {"version": "2.0", "alignment": alignment, "checks": checks}
