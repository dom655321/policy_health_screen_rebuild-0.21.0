"""Candidate window selection.

Absence is the failure mode this module exists to manage. A model asked "is this absent?"
over a 40-page document answers unreliably, and the cost of asking scales with every
control. So absence is established mechanically first:

  * the runner sweeps the whole document for every search directive, literally and
    whitespace-tolerantly;
  * if no directive matches anywhere, the control is recorded ABSENT with the full sweep
    as its evidence, and no model call is made at all;
  * only where a directive matches does the model see the surrounding windows and decide
    whether the matched text actually supports the element.

That inverts the usual arrangement. The deterministic layer proves absence; the model
only ever confirms presence, which is the question it is reliable at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WINDOW_BEFORE = 400
WINDOW_AFTER = 900
MAX_WINDOWS = 6
MAX_CONTEXT_WINDOWS = 4
# "collateralized in accordance with Section IV (I)(1)(a) of this Investment Policy" is
# how a well-drafted policy avoids repeating itself. Following the reference is the
# difference between reading the policy and reading one paragraph of it.
SECTION_REF = re.compile(
    r"Section\s+[IVXLC0-9]+(?:\s*\([A-Za-z0-9]{1,4}\))*(?:\.\d+)*", re.IGNORECASE
)


@dataclass(frozen=True)
class Sweep:
    """Result of the deterministic directive sweep over the whole document.

    `matched` reflects the primary directives only. Context windows and followed
    cross-references widen what the model sees; they must never make absence
    unprovable, or every control would find something somewhere.
    """

    windows: list[tuple[int, str]]
    trace: list[str]
    matched: bool


def whitespace_tolerant(pattern: str) -> re.Pattern[str]:
    """Compile a literal phrase so internal whitespace matches any whitespace run.

    Text extracted from a PDF wraps mid-phrase. A naive literal match misses
    "delivery versus payment basis where\\npractical" and silently converts a deficiency
    into a pass.
    """
    return re.compile(r"\s+".join(re.escape(t) for t in pattern.split()), re.IGNORECASE)


def find_all(pattern: str, document: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in whitespace_tolerant(pattern).finditer(document)]


def _merge(spans: list[tuple[int, int]], limit: int) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged[:limit]


def _follow_references(document: str, windows: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[str]]:
    """Add windows at the sections a primary window points to.

    A policy that says "collateralized in accordance with this Investment Policy" or
    "secured by obligations described in Section IV (I)(1)(a)" has satisfied the
    requirement elsewhere. Showing the model only the clause that made the reference
    guarantees a finding of absence against a policy that addressed the point properly,
    just not in that paragraph.
    """
    extra: list[tuple[int, int]] = []
    trace: list[str] = []
    seen: set[str] = set()
    for start, end in windows:
        for match in SECTION_REF.finditer(document, start, end):
            reference = " ".join(match.group(0).split()).lower()
            if reference in seen:
                continue
            seen.add(reference)
            targets = [
                span for span in find_all(match.group(0), document)
                if not (start <= span[0] < end)
            ]
            if not targets:
                continue
            trace.append(
                f"followed cross-reference {match.group(0)!r} to "
                f"{len(targets)} other location(s)"
            )
            for t_start, t_end in targets[:2]:
                extra.append((max(0, t_start - WINDOW_BEFORE),
                              min(len(document), t_end + WINDOW_AFTER)))
            if len(extra) >= MAX_CONTEXT_WINDOWS:
                return extra, trace
    return extra, trace


def sweep(
    document: str,
    directives: list[str],
    context_directives: list[str] | None = None,
    max_windows: int = MAX_WINDOWS,
) -> Sweep:
    """Sweep the full document for every directive and return the surrounding windows."""
    trace: list[str] = []
    hits: list[tuple[int, int]] = []
    for directive in directives:
        found = find_all(directive, document)
        trace.append(f"{directive!r}: {len(found)} hit(s)")
        for start, end in found:
            hits.append((max(0, start - WINDOW_BEFORE), min(len(document), end + WINDOW_AFTER)))

    matched = bool(hits)
    primary = _merge(hits, max_windows)

    context_hits: list[tuple[int, int]] = []
    for directive in context_directives or []:
        found = find_all(directive, document)
        if found:
            trace.append(f"context {directive!r}: {len(found)} hit(s)")
        for start, end in found:
            context_hits.append((max(0, start - WINDOW_BEFORE),
                                 min(len(document), end + WINDOW_AFTER)))

    followed, follow_trace = _follow_references(document, primary)
    trace.extend(follow_trace)

    if matched:
        combined = _merge(primary + context_hits[:MAX_CONTEXT_WINDOWS] + followed,
                          max_windows + MAX_CONTEXT_WINDOWS)
    else:
        combined = []
        trace.append(
            "full-document sweep matched no search directive; absence established without "
            "a model call"
        )
    windows = [(start, document[start:end]) for start, end in combined]
    return Sweep(windows=windows, trace=trace, matched=matched)
