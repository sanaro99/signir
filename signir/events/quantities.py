"""Compare supported numeric constraints without treating overlap as equality."""
from decimal import Decimal

from .schema import Quantity


def _interval(q):
    value = Decimal(q.value)
    return {
        "eq": (value, True, value, True),
        "ge": (value, True, Decimal("Infinity"), False),
        "gt": (value, False, Decimal("Infinity"), False),
        "le": (Decimal("-Infinity"), False, value, True),
        "lt": (Decimal("-Infinity"), False, value, False),
        "range": (value, True, Decimal(q.upper or q.value), True),
    }[q.relation]


def compare_quantities(a: Quantity, b: Quantity) -> dict:
    def result(status, reason):
        return {"status": status, "reason": reason}
    if (a.kind, a.unit) != (b.kind, b.unit):
        return result("UNKNOWN", "quantity_unit_or_kind")
    if a.kind == "identifier":
        return result("MATCH" if a.value == b.value else "MISMATCH", "identifier_literal")
    if "approx" in (a.relation, b.relation):
        return result("UNKNOWN", "approximate_quantity")
    x, y = _interval(a), _interval(b)
    if x == y:
        return result("MATCH", "equal_constraints")
    for left, right in [(x, y), (y, x)]:
        if left[2] < right[0] or (left[2] == right[0] and not (left[3] and right[1])):
            return result("MISMATCH", "disjoint_constraints")
    return result("UNKNOWN", "overlapping_constraints")
