"""Text normalization, and the reasons each step exists.

Every transform here is a place where a PDF can silently defeat a literal search and turn
a deficiency into a pass. A policy that reads "delivery versus payment" on the page may
arrive as "delivery ver-\\nsus payment" after extraction; the anti-pattern misses, the
control scores CONFORMING, and nobody sees it. Each step is counted so the ledger records
how much the derived text differs from what the backend produced.

Dehyphenation is the one transform that can also destroy meaning, so it is deliberately
conservative: a line-ending hyphen is joined only when the following line begins with a
lowercase letter. "dollar-weighted average maturity" keeps its hyphen; "ver-\\nsus" does
not.
"""

from __future__ import annotations

import re
import unicodedata

LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
}
PUNCTUATION = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u00a0": " ", "\u2007": " ", "\u202f": " ", "\u2009": " ",
    "\u2026": "...", "\u00ad": "",
}
HYPHEN_BREAK = re.compile(r"(\w)-[ \t]*\n[ \t]*([a-z])")
TRAILING_WS = re.compile(r"[ \t]+(\n|$)")
RUNS = re.compile(r"[ \t]{2,}")
BLANK_RUNS = re.compile(r"\n{3,}")


def _count_and_replace(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    hits = 0
    for source, target in mapping.items():
        if source in text:
            hits += text.count(source)
            text = text.replace(source, target)
    return text, hits


def normalize_page(text: str) -> tuple[str, dict[str, int]]:
    """Normalize one page of extracted text, returning the counts of each transform."""
    counts: dict[str, int] = {}

    # Count before NFKC, not after. NFKC already decomposes most ligatures, so counting
    # afterwards silently reports zero and the transform log understates how far the
    # derived text has moved from what the backend produced.
    ligatures = sum(text.count(char) for char in LIGATURES)
    if ligatures:
        counts["ligatures_expanded"] = ligatures
    text = unicodedata.normalize("NFKC", text)
    text, _ = _count_and_replace(text, LIGATURES)  # anything NFKC left behind

    text, n = _count_and_replace(text, PUNCTUATION)
    if n:
        counts["punctuation_normalized"] = n

    joined = HYPHEN_BREAK.subn(r"\1\2", text)
    if joined[1]:
        counts["line_break_hyphens_joined"] = joined[1]
    text = joined[0]

    text = TRAILING_WS.sub(r"\1", text)
    collapsed = RUNS.subn(" ", text)
    if collapsed[1]:
        counts["space_runs_collapsed"] = collapsed[1]
    text = BLANK_RUNS.sub("\n\n", collapsed[0])
    return text.strip("\n"), counts


def strip_running_heads(pages: list[str], threshold: float = 0.6) -> tuple[list[str], int]:
    """Remove headers and footers that repeat across most pages.

    A repeated running head is not policy language, but it matches search directives and
    inflates window selection. Removal is only attempted with enough pages to establish a
    pattern, and only for lines that are short enough to be furniture.
    """
    if len(pages) < 4:
        return pages, 0

    def candidates(page: str, which: str) -> list[str]:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        window = lines[:2] if which == "head" else lines[-2:]
        return [line for line in window if len(line) <= 90]

    counts: dict[str, int] = {}
    for page in pages:
        for line in set(candidates(page, "head") + candidates(page, "foot")):
            counts[line] = counts.get(line, 0) + 1

    repeated = {
        line for line, hits in counts.items()
        if hits >= max(3, int(len(pages) * threshold)) and not line.rstrip(".").isdigit()
    }
    if not repeated:
        return pages, 0

    removed = 0
    cleaned: list[str] = []
    for page in pages:
        lines = page.splitlines()
        keep: list[str] = []
        for index, line in enumerate(lines):
            near_edge = index < 2 or index >= len(lines) - 2
            if near_edge and line.strip() in repeated:
                removed += 1
                continue
            keep.append(line)
        cleaned.append("\n".join(keep))
    return cleaned, removed


def page_numbers_only(line: str) -> bool:
    stripped = line.strip().strip(".-")
    return stripped.isdigit() or bool(re.fullmatch(r"(page\s+)?\d+(\s+of\s+\d+)?", stripped, re.I))
