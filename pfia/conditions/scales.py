"""Ordinal credit-rating scales.

Rank 1 is the strongest rating. Equivalents across S&P, Moody's and Fitch share a rank,
so "A-1 or P-1 or an equivalent" compares correctly whichever agency a policy names.

Two granularities:
  NOTCH     compares ranks directly (A- is below A).
  CATEGORY  compares the letter category only; used where the Act says "without regard
            to gradations within those categories" (Sec. 2256.020(3)).
"""
from __future__ import annotations

import re

# (rank, category, aliases). Aliases are matched after normalisation (upper case, no spaces).
_LONG_TERM = [
    (1, "AAA", ("AAA", "AAA+")),
    (2, "AA", ("AA+", "AA1")), (3, "AA", ("AA", "AA2")), (4, "AA", ("AA-", "AA3")),
    (5, "A", ("A+", "A1")), (6, "A", ("A", "A2")), (7, "A", ("A-", "A3")),
    (8, "BBB", ("BBB+", "BAA1")), (9, "BBB", ("BBB", "BAA2")), (10, "BBB", ("BBB-", "BAA3")),
    (11, "BB", ("BB+", "BA1")), (12, "BB", ("BB", "BA2")), (13, "BB", ("BB-", "BA3")),
    (14, "B", ("B+", "B1")), (15, "B", ("B", "B2")), (16, "B", ("B-", "B3")),
]

_SHORT_TERM = [
    (1, "1", ("A-1+", "F1+")),
    (2, "1", ("A-1", "P-1", "F1", "PRIME-1")),
    (3, "2", ("A-2", "P-2", "F2", "PRIME-2")),
    (4, "3", ("A-3", "P-3", "F3", "PRIME-3")),
    (5, "NP", ("B", "C", "NP", "NOT PRIME")),
]

# Public funds pools and money funds: only the top rating is eligible (Sec. 2256.019).
_POOL = [
    (1, "AAA", ("AAA", "AAAM", "AAA-M", "AAAF", "AAA-MMF", "AAAMMF", "AAA-MF", "AAAMF", "AAAF/S1", "AAA/S1")),
    (2, "AA", ("AAM", "AA-M", "AAF", "AA+M", "AA+F", "AA-MMF", "AA-MF", "AA1-MF")),
]

# Legacy bank certificate-of-deposit ratings ("at least 1", Sec. 2256.020(2)).
# INTERPRETIVE: the Act does not name this scale. "1" is read as the top short-term deposit
# or CD rating of any NRSRO (A-1, P-1, F1 or better); see condition NCD-01.
_CD = [(1, "1", ("1", "A-1+", "A-1", "P-1", "F1+", "F1")), (2, "2", ("2", "A-2", "P-2", "F2"))]

SCALES = {"LONG_TERM": _LONG_TERM, "SHORT_TERM": _SHORT_TERM, "POOL": _POOL, "CD": _CD}


class UnknownRating(ValueError):
    """A rating string that does not appear on the named scale. Never guessed."""


def _norm(value: str) -> str:
    v = value.strip().upper()
    v = re.sub(r"\s+", "", v)
    v = v.replace("–", "-").replace("—", "-")
    return v


def _index(scale: str) -> dict[str, tuple[int, str]]:
    table = {}
    for rank, category, aliases in SCALES[scale]:
        for alias in aliases:
            table[_norm(alias)] = (rank, category)
    return table


_INDEX = {name: _index(name) for name in SCALES}


def rank(value: str, scale: str) -> int:
    """Ordinal rank of a rating on a scale (1 = strongest). Raises UnknownRating."""
    hit = _INDEX[scale].get(_norm(value))
    if hit is None:
        raise UnknownRating(f"{value!r} is not on the {scale} scale")
    return hit[0]


def category(value: str, scale: str) -> str:
    hit = _INDEX[scale].get(_norm(value))
    if hit is None:
        raise UnknownRating(f"{value!r} is not on the {scale} scale")
    return hit[1]


def _weakest_notch(cat: str, scale: str) -> int:
    return max(r for r, c, _ in SCALES[scale] if c == cat)


def compare(policy_floor: str, statutory_floor: str, scale: str, granularity: str = "NOTCH") -> int:
    """Compare a policy's rating floor with the statutory floor.

    Returns -1 if the policy floor is stronger (stricter), 0 if equal, 1 if weaker (the
    policy would admit a rating the statute does not).

    Under CATEGORY granularity the statutory floor is the weakest notch of its category,
    so "two highest categories" (AA) is met exactly by AA- and exceeded by AA or better.
    """
    p = rank(policy_floor, scale)
    s = _weakest_notch(category(statutory_floor, scale), scale) if granularity == "CATEGORY" else rank(statutory_floor, scale)
    return (p > s) - (p < s)


def stronger(a: str, b: str, scale: str) -> str:
    """The stronger of two ratings on a scale (used for effective limits)."""
    return a if rank(a, scale) <= rank(b, scale) else b
