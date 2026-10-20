"""Global assignment using lexical anchors only, with explicit null and tie handling."""
from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from .schema import Graph


def labels(graph, event):
    mentions = {m.id: m for m in graph.mentions}
    return Counter(mentions[mid].label.casefold() for mid in event.participants
                   if not mentions[mid].alternatives)


def align_events(english: Graph, gloss: Graph) -> dict:
    a, b = english.events, gloss.events
    n, m = len(a), len(b)
    weights = np.zeros((n + m, n + m))
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            left, right = labels(english, x), labels(gloss, y)
            shared = sum((left & right).values())
            same_predicate = (x.predicate.casefold() == y.predicate.casefold()
                              and not x.alternatives and not y.alternatives)
            # Two independent participant anchors can identify a changed predicate.
            weights[i, j] = (4 + shared if same_predicate else
                             shared if shared >= 2 else 0)

    def solve(matrix):
        rows, cols = linear_sum_assignment(matrix, maximize=True)
        return float(matrix[rows, cols].sum()), list(zip(rows.tolist(), cols.tolist()))

    total, chosen = solve(weights)
    pairs, ambiguous = [], []
    margins = {}
    for i, j in chosen:
        if i >= n or j >= m or weights[i, j] <= 0:
            continue
        forbidden = weights.copy()
        forbidden[i, j] = -1e9
        alternative, _ = solve(forbidden)
        margin = total - alternative
        key = f"{a[i].id}:{b[j].id}"
        margins[key] = margin
        if margin < 0.5:
            ambiguous.append([a[i].id, b[j].id])
        else:
            pairs.append([a[i].id, b[j].id])
    used_a, used_b = {x for x, _ in pairs}, {y for _, y in pairs}
    return {
        "pairs": pairs,
        "ambiguous_candidates": ambiguous,
        "unmatched_english": [x.id for x in a if x.id not in used_a],
        "unmatched_gloss": [x.id for x in b if x.id not in used_b],
        "assignment_margins": margins,
        "method": "lexical_assignment_v1",
    }
