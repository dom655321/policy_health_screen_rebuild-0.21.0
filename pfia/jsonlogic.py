"""Deterministic JsonLogic subset evaluator.

Standard library only. Deliberately narrow: the register's predicate language is
data, and the set of operators it may use is closed so that a register authored by
an analyst cannot introduce arbitrary behaviour into the evaluator.

Supported operators
-------------------
var, missing, ==, !=, <, <=, >, >=, and, or, !, !!, in, some, all, none, if

`{"var": ""}` resolves to the current data context, which is what `some`/`all`/`none`
bind each collection item to.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .errors import PredicateError

_MISSING = object()


class _Unknown:
    """Third truth value for a fact the reviewer has not supplied.

    Two-valued logic silently answers "no" for an unanswered profile question, which
    quietly drops the controls that depend on it out of the applicable set. A reviewer
    reading the result cannot tell "this control does not apply to you" from "nobody
    told us". UNKNOWN keeps those apart all the way to the finding.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        raise PredicateError(
            "UNKNOWN has no boolean value; use test_tri() and handle the third case"
        )

    def __repr__(self) -> str:
        return "UNKNOWN"


UNKNOWN = _Unknown()


def is_unknown(value: Any) -> bool:
    return value is UNKNOWN


def _resolve_var(path: Any, data: Any) -> Any:
    if path in ("", None):
        return data
    if not isinstance(path, str):
        raise PredicateError(f"var path must be a string, got {type(path).__name__}")
    node: Any = data
    for part in path.split("."):
        if isinstance(node, Mapping):
            node = node.get(part, _MISSING)
        elif isinstance(node, Sequence) and not isinstance(node, str) and part.isdigit():
            idx = int(part)
            node = node[idx] if 0 <= idx < len(node) else _MISSING
        else:
            return None
        if node is _MISSING:
            return None
    return node


def _truthy(value: Any) -> Any:
    """Truthiness that preserves UNKNOWN rather than collapsing it to False."""
    if value is UNKNOWN:
        return UNKNOWN
    if isinstance(value, (list, tuple, dict, str)):
        return len(value) > 0
    return bool(value)


def _compare(op: str, args: list[Any]) -> Any:
    if len(args) != 2:
        raise PredicateError(f"operator {op!r} requires exactly 2 arguments")
    left, right = args
    if left is UNKNOWN or right is UNKNOWN:
        # An unanswered fact makes the comparison unanswerable, not false.
        return UNKNOWN
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if left is None or right is None:
        # Absent facts never satisfy an ordering comparison. Fail closed.
        return False
    try:
        return {
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
        }[op]
    except TypeError as exc:  # incomparable types
        raise PredicateError(f"cannot compare {left!r} and {right!r} with {op!r}") from exc


def evaluate(expr: Any, data: Any) -> Any:
    """Evaluate a JsonLogic expression against `data`."""
    if expr is None or isinstance(expr, (str, int, float, bool)):
        return expr
    if isinstance(expr, list):
        return [evaluate(item, data) for item in expr]
    if not isinstance(expr, Mapping):
        raise PredicateError(f"unsupported expression node: {type(expr).__name__}")
    if len(expr) != 1:
        raise PredicateError(f"expression node must have exactly one operator, got {list(expr)}")

    op, raw_args = next(iter(expr.items()))
    args = raw_args if isinstance(raw_args, list) else [raw_args]

    if op == "var":
        return _resolve_var(evaluate(args[0], data) if args else "", data)
    if op == "missing":
        keys = evaluate(args, data)
        flat = keys[0] if len(keys) == 1 and isinstance(keys[0], list) else keys
        return [k for k in flat if _resolve_var(k, data) in (None, "")]
    if op in ("==", "!=", "<", "<=", ">", ">="):
        return _compare(op, [evaluate(a, data) for a in args])
    if op == "and":
        # Kleene semantics: a definite False still decides the conjunction; otherwise an
        # unanswered operand leaves the whole expression unanswered.
        unknown = False
        for a in args:
            value = _truthy(evaluate(a, data))
            if value is UNKNOWN:
                unknown = True
            elif not value:
                return False
        return UNKNOWN if unknown else True
    if op == "or":
        unknown = False
        for a in args:
            value = _truthy(evaluate(a, data))
            if value is UNKNOWN:
                unknown = True
            elif value:
                return True
        return UNKNOWN if unknown else False
    if op == "!":
        value = _truthy(evaluate(args[0], data))
        return UNKNOWN if value is UNKNOWN else not value
    if op == "!!":
        return _truthy(evaluate(args[0], data))
    if op == "in":
        needle, haystack = evaluate(args[0], data), evaluate(args[1], data)
        if needle is UNKNOWN or haystack is UNKNOWN:
            return UNKNOWN
        if haystack is None:
            return False
        return needle in haystack
    if op in ("some", "all", "none"):
        collection = evaluate(args[0], data)
        if collection is UNKNOWN:
            return UNKNOWN
        if collection is None:
            collection = []
        if not isinstance(collection, (list, tuple)):
            raise PredicateError(f"{op!r} requires an array, got {type(collection).__name__}")
        test = args[1]
        hits = [_truthy(evaluate(test, item)) for item in collection]
        unknown = any(h is UNKNOWN for h in hits)
        definite = [h for h in hits if h is not UNKNOWN]
        if op == "some":
            if any(definite):
                return True
            return UNKNOWN if unknown else False
        if op == "all":
            if not collection:
                return False
            if any(h is False for h in definite):
                return False
            return UNKNOWN if unknown else True
        if any(definite):
            return False
        return UNKNOWN if unknown else True
    if op == "if":
        for i in range(0, len(args) - 1, 2):
            if _truthy(evaluate(args[i], data)):
                return evaluate(args[i + 1], data)
        return evaluate(args[-1], data) if len(args) % 2 else None

    raise PredicateError(f"unsupported operator {op!r}")


def test(expr: Any, data: Any) -> bool:
    """Evaluate `expr` as a two-valued predicate, treating UNKNOWN as False.

    Only for callers that genuinely have no third branch. Anything that reports to a
    reviewer should use test_tri().
    """
    value = test_tri(expr, data)
    return False if value is UNKNOWN else value


def test_tri(expr: Any, data: Any) -> Any:
    """Evaluate `expr` to True, False or UNKNOWN."""
    return _truthy(evaluate(expr, data))
