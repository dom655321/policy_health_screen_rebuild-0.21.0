"""Deterministic evaluation of authorized-investment conditions.

Input is one extracted fact per condition. Output is a state per condition and a
categorical status per instrument (ADR 0010). No weights, fractions or indices.

Fact shape (all keys optional; absence of the whole fact is UNKNOWN, never SILENT):

    {"stated": bool,          policy addresses the condition at all
     "value": ...,            number | rating string | list of codes / alternative ids
     "unit": "days",          CAP / FLOOR
     "inclusive": True,       CAP: policy bound includes the figure ("not to exceed")
     "agencies": 2,           RATING_FLOOR: agencies the policy requires
     "basis": "CONTINUOUS",   RATING_FLOOR: AT_PURCHASE | CONTINUOUS
     "contradicted": bool,    REQUIRED: affirmative contrary language in the clause
     "outside": bool,         ANY_OF: policy states a path the statute does not offer
     "authorized": bool,      PROHIBITED: policy authorizes the prohibited item
     "excluded": bool,        PROHIBITED: policy expressly excludes it
     "by_reference": bool,    incorporation clause in scope (ADR 0007)
     "span": ...}             evidence locator, carried through untouched
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from . import scales
from .catalogue import Catalogue, Condition

CONFORMING = "CONFORMING"
STRICTER = "STRICTER"
BY_REFERENCE = "BY_REFERENCE"
SILENT = "SILENT"
CONTRADICTED = "CONTRADICTED"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNRESOLVED = "APPLICABILITY_UNRESOLVED"

SATISFIED = frozenset({CONFORMING, STRICTER, BY_REFERENCE})
_SEVERITY = {CONTRADICTED: 3, UNKNOWN: 2, CONFORMING: 1, STRICTER: 0}

# Exact conversions only. Days against months or years is approximate and is refused
# near the limit rather than rounded into a verdict.
_EXACT = {("years", "months"): 12.0, ("months", "years"): 1 / 12.0}
_APPROX_DAYS = {"days": 1.0, "months": 30.4375, "years": 365.25}
_AMBIGUITY_DAYS = 3.0


@dataclass(frozen=True)
class ConditionResult:
    condition_id: str
    state: str
    detail: str
    policy_value: Any = None
    statutory_value: Any = None
    effective_value: Any = None
    span: Any = None

    @property
    def counts(self) -> bool:
        return self.state not in (NOT_APPLICABLE, UNRESOLVED)


@dataclass
class InstrumentResult:
    code: str
    status: str
    contradicted: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    not_restated: list[str] = field(default_factory=list)
    results: list[ConditionResult] = field(default_factory=list)


def _combine(states: Iterable[str]) -> str:
    states = list(states)
    return max(states, key=lambda s: _SEVERITY[s]) if states else CONFORMING


# ---------------------------------------------------------------- unit handling

def _convert(value: float, src: str, dst: str) -> tuple[float, bool]:
    """Convert value from src to dst unit. Returns (value, exact)."""
    if src == dst:
        return value, True
    if (src, dst) in _EXACT:
        return value * _EXACT[(src, dst)], True
    if src in _APPROX_DAYS and dst in _APPROX_DAYS:
        return value * _APPROX_DAYS[src] / _APPROX_DAYS[dst], False
    if src.startswith("pct") or dst.startswith("pct"):
        # A percentage is only comparable on the same base: 15 percent of the portfolio is
        # not 15 percent of the monthly average fund balance excluding bond proceeds.
        raise ValueError(f"percentage base {src!r} does not match the statutory base {dst!r}")
    raise ValueError(f"cannot convert {src} to {dst}")


def _near_limit(value: float, limit: float, unit: str) -> bool:
    days = _APPROX_DAYS.get(unit)
    return days is not None and abs(value - limit) * days <= _AMBIGUITY_DAYS


# ---------------------------------------------------------------- modes

def _cap(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    limit, unit, strict = float(test["limit"]), test["unit"], bool(test.get("strict", False))
    try:
        v, exact = _convert(float(fact["value"]), fact.get("unit", unit), unit)
    except (KeyError, TypeError, ValueError) as exc:
        return UNKNOWN, f"figure not comparable: {exc}", None
    inclusive = bool(fact.get("inclusive", True))
    if not exact and _near_limit(v, limit, unit):
        return UNKNOWN, f"{fact['value']} {fact.get('unit')} is within {_AMBIGUITY_DAYS:g} days of {limit:g} {unit} after an approximate unit conversion", None
    statutory = {"limit": limit, "unit": unit, "strict": strict}
    if v > limit:
        return CONTRADICTED, f"policy admits up to {v:g} {unit}; statute caps at {limit:g}", statutory
    if v < limit:
        return STRICTER, f"policy caps at {v:g} {unit}, inside the statutory {limit:g}", {"limit": v, "unit": unit, "strict": not inclusive}
    if strict and inclusive:
        return CONTRADICTED, f"policy admits exactly {limit:g} {unit}; statute requires less than {limit:g}", statutory
    if not strict and not inclusive:
        return STRICTER, f"policy requires less than {limit:g} {unit}; statute allows {limit:g}", {"limit": v, "unit": unit, "strict": True}
    return CONFORMING, f"policy cap equals the statutory {limit:g} {unit}", statutory


def _floor(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    limit, unit = float(test["limit"]), test["unit"]
    try:
        v, _ = _convert(float(fact["value"]), fact.get("unit", unit), unit)
    except (KeyError, TypeError, ValueError) as exc:
        return UNKNOWN, f"figure not comparable: {exc}", None
    if v < limit:
        return CONTRADICTED, f"policy requires only {v:g}; statute requires at least {limit:g} {unit}", {"limit": limit, "unit": unit}
    if v > limit:
        return STRICTER, f"policy requires {v:g}, above the statutory {limit:g} {unit}", {"limit": v, "unit": unit}
    return CONFORMING, f"policy floor equals the statutory {limit:g} {unit}", {"limit": limit, "unit": unit}


def _rating(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    scale, floor, gran = test["scale"], test["floor"], test.get("granularity", "NOTCH")
    min_ag, basis = int(test.get("min_agencies", 1)), test.get("basis", "AT_PURCHASE")
    parts: list[tuple[str, str]] = []
    effective = {"floor": floor, "scale": scale, "granularity": gran, "min_agencies": min_ag, "basis": basis}
    try:
        cmp = scales.compare(str(fact["value"]), floor, scale, gran)
    except (KeyError, scales.UnknownRating) as exc:
        return UNKNOWN, f"rating not comparable: {exc}", None
    if cmp > 0:
        parts.append((CONTRADICTED, f"policy floor {fact['value']} is below the statutory {floor}"))
    elif cmp < 0:
        parts.append((STRICTER, f"policy floor {fact['value']} is above the statutory {floor}"))
        effective["floor"] = str(fact["value"])
        effective["granularity"] = "NOTCH"
    else:
        parts.append((CONFORMING, f"policy floor {fact['value']} meets the statutory {floor}"))
    if "agencies" in fact:
        ag = int(fact["agencies"])
        if ag < min_ag:
            parts.append((CONTRADICTED, f"policy requires {ag} agency rating(s); statute requires {min_ag}"))
        elif ag > min_ag:
            parts.append((STRICTER, f"policy requires {ag} agency ratings"))
            effective["min_agencies"] = ag
    pb = fact.get("basis")
    if pb == "AT_PURCHASE" and basis == "CONTINUOUS":
        parts.append((CONTRADICTED, "policy tests the rating at purchase only; statute requires it continuously"))
    elif pb == "CONTINUOUS" and basis == "AT_PURCHASE":
        parts.append((STRICTER, "policy requires the rating continuously"))
        effective["basis"] = "CONTINUOUS"
    state = _combine(s for s, _ in parts)
    detail = "; ".join(d for s, d in parts)
    if state == CONTRADICTED:
        effective = {"floor": floor, "scale": scale, "granularity": gran, "min_agencies": min_ag, "basis": basis}
    return state, detail, effective


def _subset(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    allowed = list(test["allowed"])
    stated = fact.get("value")
    if not isinstance(stated, list) or not stated:
        return UNKNOWN, "stated set missing or empty", None
    outside = [s for s in stated if isinstance(s, str) and s.startswith("OTHER")]
    malformed = [s for s in stated if s not in allowed and s not in outside]
    if outside:
        return CONTRADICTED, f"policy permits items outside the statutory set: {', '.join(outside)}", allowed
    if malformed:
        return UNKNOWN, f"extraction returned codes outside the vocabulary: {', '.join(map(str, malformed))}", None
    if set(stated) < set(allowed):
        return STRICTER, f"policy permits {len(set(stated))} of {len(allowed)} statutory items", sorted(set(stated), key=allowed.index)
    return CONFORMING, "policy permits the full statutory set", allowed


def _any_of(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    ids = [a["id"] for a in test["alternatives"]]
    if fact.get("outside"):
        return CONTRADICTED, "policy states a path the statute does not offer", ids
    stated = fact.get("value")
    if not isinstance(stated, list) or not stated:
        return UNKNOWN, "stated alternatives missing or empty", None
    bad = [s for s in stated if s not in ids]
    if bad:
        return UNKNOWN, f"extraction returned unknown alternatives: {', '.join(map(str, bad))}", None
    if set(stated) < set(ids):
        return STRICTER, f"policy permits {len(set(stated))} of {len(ids)} statutory paths", [i for i in ids if i in stated]
    return CONFORMING, "policy permits every statutory path", ids


def _required(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    if fact.get("contradicted"):
        return CONTRADICTED, "policy language contradicts the requirement", True
    return CONFORMING, "policy states the requirement", True


def _prohibited(test: Mapping[str, Any], fact: Mapping[str, Any]) -> tuple[str, str, Any]:
    if fact.get("authorized"):
        return CONTRADICTED, "policy authorizes an item the statute prohibits", "PROHIBITED"
    return CONFORMING, "policy expressly excludes the item", "PROHIBITED"


_MODES = {"CAP": _cap, "FLOOR": _floor, "RATING_FLOOR": _rating, "SUBSET": _subset,
          "ANY_OF": _any_of, "REQUIRED": _required, "PROHIBITED": _prohibited}


def _statutory(test: Mapping[str, Any]) -> Any:
    mode = test["mode"]
    if mode in ("CAP", "FLOOR"):
        return {"limit": test["limit"], "unit": test["unit"], **({"strict": test.get("strict", False)} if mode == "CAP" else {})}
    if mode == "RATING_FLOOR":
        return {"floor": test["floor"], "scale": test["scale"], "granularity": test.get("granularity", "NOTCH"),
                "min_agencies": test.get("min_agencies", 1), "basis": test.get("basis", "AT_PURCHASE")}
    if mode == "SUBSET":
        return list(test["allowed"])
    if mode == "ANY_OF":
        return [a["id"] for a in test["alternatives"]]
    return "PROHIBITED" if mode == "PROHIBITED" else True


# ---------------------------------------------------------------- public API

def evaluate_condition(cond: Condition, fact: Mapping[str, Any] | None,
                       activation: Mapping[str, Any] | None = None) -> ConditionResult:
    statutory = _statutory(cond.test)
    span = fact.get("span") if fact else None

    if cond.activation:
        key = cond.activation["fact"]
        active = (activation or {}).get(key)
        if active is False:
            return ConditionResult(cond.id, NOT_APPLICABLE, f"inactive: {key} is false", statutory_value=statutory)
        if active is None and not (fact and (fact.get("stated") or fact.get("authorized"))):
            return ConditionResult(cond.id, UNRESOLVED, f"activation fact {key} not answered", statutory_value=statutory)

    if fact is None:
        return ConditionResult(cond.id, UNKNOWN, "no extracted fact for this condition", statutory_value=statutory)

    mode = cond.mode
    if mode == "PROHIBITED":
        addressed = bool(fact.get("authorized") or fact.get("excluded"))
    else:
        addressed = bool(fact.get("stated"))
    if not addressed:
        if fact.get("by_reference"):
            return ConditionResult(cond.id, BY_REFERENCE, "satisfied by an in-scope incorporation clause",
                                   statutory_value=statutory, effective_value=statutory, span=span)
        if mode == "PROHIBITED":
            # A prohibition binds regardless; silence authorizes nothing.
            return ConditionResult(cond.id, SILENT, "policy neither authorizes nor excludes the item",
                                   statutory_value=statutory, effective_value=statutory, span=span)
        return ConditionResult(cond.id, SILENT, "policy does not address the condition",
                               statutory_value=statutory, effective_value=statutory, span=span)

    state, detail, effective = _MODES[mode](cond.test, fact)
    if state == CONTRADICTED:
        effective = statutory
    return ConditionResult(cond.id, state, detail, policy_value=fact.get("value"),
                           statutory_value=statutory, effective_value=effective, span=span)


def evaluate_instrument(catalogue: Catalogue, code: str, facts: Mapping[str, Mapping[str, Any]],
                        activation: Mapping[str, Any] | None = None) -> InstrumentResult:
    """Evaluate every condition of an authorized instrument (inherited conditions included).

    NOT_REVIEWED     the instrument is out of scope (no active conditions after review).
    CONFLICTS        any active condition is CONTRADICTED; the result names each one.
    REVIEW_REQUIRED  any condition is UNKNOWN or its applicability is unanswered, and none
                     is CONTRADICTED.
    ALIGNED          otherwise. Conditions the policy does not restate are listed in
                     not_restated; they never change the status, because the statute binds.
    """
    if catalogue.instruments[code].not_reviewed:
        # Out of scope by team decision. Never ALIGNED: an empty set of conditions is not a
        # clean result, it is the absence of one.
        return InstrumentResult(code, "NOT_REVIEWED")
    conds = catalogue.conditions_for(code)
    results = [evaluate_condition(c, facts.get(c.id), activation) for c in conds]
    active = [r for r in results if r.counts]
    contradicted = [r.condition_id for r in active if r.state == CONTRADICTED]
    unknown = [r.condition_id for r in active if r.state == UNKNOWN]
    unresolved = [r.condition_id for r in results if r.state == UNRESOLVED]
    not_restated = [r.condition_id for r in active if r.state == SILENT]
    status = "CONFLICTS" if contradicted else ("REVIEW_REQUIRED" if unknown or unresolved else "ALIGNED")
    return InstrumentResult(code, status, contradicted, unknown, unresolved, not_restated, results)
