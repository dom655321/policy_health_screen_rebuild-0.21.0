"""Extraction seam.

The model's only job is span extraction and fact assertion. It never returns a
verdict. Any extractor that emits `ControlExtraction` can drive the evaluator, which
is what keeps the pipeline model-agnostic: swapping Gemini for Claude or a local
model changes this layer and nothing downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from .errors import ExtractionError
from .model import Control


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str


@dataclass
class ControlExtraction:
    control_id: str
    elements_satisfied: dict[str, bool] = field(default_factory=dict)
    spans: dict[str, list[Span]] = field(default_factory=dict)
    anti_pattern_hits: list[Span] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    discarded_claims: list[dict[str, Any]] = field(default_factory=list)
    windows_found: bool = True
    retrieval_trace: list[str] = field(default_factory=list)
    extractor: str = "unknown"

    def any_span(self) -> bool:
        return any(self.spans.values())


class Extractor(Protocol):
    name: str

    def extract(self, control: Control, document: str) -> ControlExtraction: ...


def _find(pattern: str, document: str) -> list[Span]:
    """Whitespace-tolerant literal search.

    Text extracted from a PDF wraps mid-phrase, so a naive literal match misses
    "delivery versus payment basis where\npractical" and silently converts a
    deficiency into a pass. Internal whitespace in the pattern matches any run of
    whitespace in the document.
    """
    tokens = [re.escape(t) for t in pattern.split()]
    rx = re.compile(r"\s+".join(tokens), re.IGNORECASE)
    return [Span(m.start(), m.end(), document[m.start(): m.end()]) for m in rx.finditer(document)]


class KeywordExtractor:
    """Deterministic baseline extractor.

    Search directives and anti-patterns are matched literally. Element-level
    assertions cannot be tested this way, so every element is marked satisfied when
    any directive matches. This is a CI fixture driver and a smoke test for register
    wiring, not a review-grade extractor.
    """

    name = "keyword-baseline"

    def extract(self, control: Control, document: str) -> ControlExtraction:
        directives: Iterable[str] = control.test.get("search_directives", [])
        anti: Iterable[str] = control.test.get("anti_patterns", [])
        result = ControlExtraction(control_id=control.control_id, extractor=self.name)
        hits: list[Span] = []
        for directive in directives:
            found = _find(directive, document)
            result.retrieval_trace.append(f"{directive!r}: {len(found)} hit(s)")
            hits.extend(found)
        for pattern in anti:
            result.anti_pattern_hits.extend(_find(pattern, document))
        for element in control.elements:
            result.elements_satisfied[element.id] = bool(hits)
            result.spans[element.id] = hits[:3]
        return result


class PrecomputedExtractor:
    """Replays extraction payloads produced upstream by a model adapter.

    Payload shape (one object per control id):
        {"elements_satisfied": {"e1": true}, "facts": {...},
         "spans": {"e1": [[start, end]]}, "anti_pattern_hits": [[start, end]]}
    """

    name = "precomputed"

    def __init__(self, payload: Mapping[str, Mapping[str, Any]], source: str = "precomputed"):
        self._payload = payload
        self.name = source

    def extract(self, control: Control, document: str) -> ControlExtraction:
        raw = self._payload.get(control.control_id)
        if raw is None:
            return ControlExtraction(control_id=control.control_id, extractor=self.name,
                                     retrieval_trace=["no extraction payload supplied"])
        satisfied = dict(raw.get("elements_satisfied", {}))
        unknown = set(satisfied) - {e.id for e in control.elements}
        if unknown:
            raise ExtractionError(f"{control.control_id}: payload references unknown elements {sorted(unknown)}")
        spans = {
            eid: [Span(s, e, document[s:e]) for s, e in pairs]
            for eid, pairs in raw.get("spans", {}).items()
        }
        anti = [Span(s, e, document[s:e]) for s, e in raw.get("anti_pattern_hits", [])]
        return ControlExtraction(
            control_id=control.control_id,
            elements_satisfied=satisfied,
            spans=spans,
            anti_pattern_hits=anti,
            facts=dict(raw.get("facts", {})),
            discarded_claims=list(raw.get("discarded_claims", [])),
            windows_found=bool(raw.get("windows_found", True)),
            retrieval_trace=list(raw.get("retrieval_trace", [])),
            extractor=self.name,
        )


class NullExtractor:
    """Finds nothing. Used to test applicability gating in isolation."""

    name = "null"

    def extract(self, control: Control, document: str) -> ControlExtraction:
        return ControlExtraction(control_id=control.control_id, extractor=self.name)
