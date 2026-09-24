"""A small, deliberately non-Turing-complete condition language.

Rules are written in YAML, never in Python (per the brief), so conditions
must be safe to evaluate without exec/eval. A condition is either a leaf
comparison against a field in the evaluation context, or a boolean
combinator (`all` / `any` / `not`) over other conditions.

Leaf shape:      {"field": "income", "op": "lt", "value": 10000}
Combinator shape: {"all": [<condition>, <condition>, ...]}
                   {"any": [<condition>, <condition>, ...]}
                   {"not": <condition>}
"""

from __future__ import annotations

import operator
from typing import Any

_OPS: dict[str, Any] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
}


class ConditionError(ValueError):
    pass


def referenced_fields(condition: dict[str, Any]) -> set[str]:
    if "all" in condition:
        return {f for c in condition["all"] for f in referenced_fields(c)}
    if "any" in condition:
        return {f for c in condition["any"] for f in referenced_fields(c)}
    if "not" in condition:
        return referenced_fields(condition["not"])
    return {condition["field"]}


def evaluate_condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if "all" in condition:
        return all(evaluate_condition(c, context) for c in condition["all"])
    if "any" in condition:
        return any(evaluate_condition(c, context) for c in condition["any"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], context)

    if "field" not in condition or "op" not in condition:
        raise ConditionError(f"leaf condition missing 'field' or 'op': {condition!r}")

    field = condition["field"]
    op = condition["op"]

    if op == "exists":
        return context.get(field) is not None

    if op not in _OPS:
        raise ConditionError(f"unknown operator: {op!r}")

    actual = context.get(field)
    if actual is None:
        return False

    expected = condition.get("value")
    try:
        return bool(_OPS[op](actual, expected))
    except TypeError as exc:
        raise ConditionError(
            f"cannot apply operator {op!r} to field {field!r}: {exc}"
        ) from exc
