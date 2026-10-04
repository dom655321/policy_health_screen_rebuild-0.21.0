"""Response validation and span verification.

Model-reported character offsets are never trusted. The model returns a quote; this
module locates that quote in the document itself and derives the offsets. A quote that
cannot be located is treated as fabricated: the element claim is discarded, the element
is marked unsupported, and the discard is recorded in the retrieval trace.

This is the single most important control on the model in the whole pipeline. It converts
"the model asserted X" into "the document contains X at offset N", which is the only form
of evidence that survives a client challenge.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..errors import ExtractionError
from ..model import Control
from .base import ElementClaim, ModelResponse
from .retrieval import find_all


def normalize_response(control: Control, raw: Any) -> ModelResponse:
    """Coerce a provider payload into ModelResponse, discarding anything unrecognized.

    Tolerant of a bare array, because a cached or replayed payload may have been captured
    before the provider layer normalized it, and because this function is the one place
    every extraction path converges on.
    """
    if isinstance(raw, list):
        raw = {"elements": raw}
    if not isinstance(raw, Mapping):
        raise ExtractionError(
            f"{control.control_id}: extraction payload is a {type(raw).__name__}, "
            "expected an object with an 'elements' array"
        )
    known = {e.id for e in control.elements}
    claims: list[ElementClaim] = []
    seen: set[str] = set()
    for item in raw.get("elements", []) or []:
        if not isinstance(item, Mapping):
            continue
        # Models name this field variously. The content is unambiguous, so accepting the
        # synonyms is right; silently dropping a correct answer over a key name is not.
        element_id = str(
            item.get("id")
            or item.get("element_id")
            or item.get("elementId")
            or item.get("element")
            or ""
        )
        if element_id not in known or element_id in seen:
            continue
        seen.add(element_id)
        claims.append(
            ElementClaim(
                element_id=element_id,
                supported=bool(item.get("supported", False)),
                quote=str(item.get("quote", "") or ""),
                note=str(item.get("note", "") or "")[:280],
            )
        )
    facts = raw.get("facts") or {}
    return ModelResponse(
        control_id=control.control_id,
        elements=claims,
        facts=dict(facts) if isinstance(facts, Mapping) else {},
        raw=dict(raw),
    )


def verify(control: Control, response: ModelResponse, document: str) -> dict[str, Any]:
    """Verify quotes against the document and emit an extraction payload entry."""
    satisfied: dict[str, bool] = {}
    spans: dict[str, list[list[int]]] = {}
    trace: list[str] = []
    # Discards are recorded structurally, not only as prose in the trace. The citation
    # verification line in a client report has to be able to name what was thrown away.
    discarded: list[dict[str, Any]] = []

    claimed = {c.element_id: c for c in response.elements}
    for element in control.elements:
        if element.negative:
            continue  # resolved deterministically by negative_element_results
        if element.conditional:
            continue  # resolved from the extracted figure by the evaluator
        claim = claimed.get(element.id)
        if claim is None:
            satisfied[element.id] = False
            trace.append(f"{element.id}: no claim returned; treated as unsupported")
            continue
        if not claim.supported:
            satisfied[element.id] = False
            if claim.note:
                trace.append(f"{element.id}: unsupported - {claim.note}")
            continue

        quote = claim.quote.strip()
        if not quote:
            satisfied[element.id] = False
            discarded.append({"element_id": element.id, "reason": "no_quote", "quote": ""})
            trace.append(f"{element.id}: claimed supported without a quote; discarded")
            continue

        located = find_all(quote, document)
        if not located:
            satisfied[element.id] = False
            discarded.append({"element_id": element.id, "reason": "quote_not_in_document",
                              "quote": quote[:160]})
            trace.append(
                f"{element.id}: quoted text not found in the document; claim discarded "
                f"(quote begins {quote[:60]!r})"
            )
            continue

        satisfied[element.id] = True
        spans[element.id] = [[start, end] for start, end in located[:3]]
        trace.append(f"{element.id}: supported, quote verified at offset {located[0][0]}")

    return {
        "elements_satisfied": satisfied,
        "spans": spans,
        "facts": response.facts,
        "discarded_claims": discarded,
        "retrieval_trace": trace,
    }


def negative_element_results(control: Control, document: str) -> dict[str, Any]:
    """Resolve negative elements by searching for the language that would defeat them.

    Subject to the control's `anti_pattern_anchors`, like anti-patterns: a Schedule B
    conformity element's `contradicted_by` is the same library (test_instruments invariant).
    """
    satisfied: dict[str, bool] = {}
    spans: dict[str, list[list[int]]] = {}
    trace: list[str] = []
    for element in control.elements:
        if element.conditional:
            # Satisfied unless a stated figure conflicts; the evaluator decides from the
            # extracted facts, so nothing is asserted here.
            satisfied[element.id] = True
            continue
        if not element.negative:
            continue
        hits: list[list[int]] = []
        for phrase in element.contradicted_by:
            hits.extend([start, end] for start, end in find_all(phrase, document)
                        if anchored(control, document, start, end))
        satisfied[element.id] = not hits
        if hits:
            spans[element.id] = hits[:3]
            trace.append(
                f"{element.id}: contradicting language located at offset {hits[0][0]}; "
                "element unsatisfied"
            )
        else:
            trace.append(
                f"{element.id}: no contradicting language in the document; "
                "element satisfied by absence"
            )
    return {"elements_satisfied": satisfied, "spans": spans, "retrieval_trace": trace}


_BOUNDARY = re.compile(r"(?<=[.;])\s+|\n\s*\n")


def _context(document: str, start: int, end: int) -> str:
    """The sentence containing [start, end) plus the sentence before it."""
    bounds = [0] + [m.end() for m in _BOUNDARY.finditer(document)] + [len(document)]
    i = max(k for k, b in enumerate(bounds) if b <= start)
    j = min(k for k, b in enumerate(bounds) if b >= end)
    return document[bounds[max(0, i - 1)]:bounds[j]]


def anchored(control: Control, document: str, start: int, end: int) -> bool:
    """Whether a matched phrase is about this control's subject.

    Most anti-patterns are specific enough to mean one thing wherever they appear. A few
    are generic qualifiers ("reviewed as needed", "where practical", "speculative") that
    also occur in unrelated clauses; those controls declare `anti_pattern_anchors`, and a
    hit counts only when an anchor term appears in the same or the preceding sentence.
    Controls without anchors match document-wide. Element audit EA-2026-09-27.
    """
    anchors = control.test.get("anti_pattern_anchors") or []
    if not anchors:
        return True
    text = _context(document, start, end)
    return any(find_all(a, text) for a in anchors)


def anti_pattern_hits(control: Control, document: str) -> list[list[int]]:
    """Locate anti-patterns deterministically. The model is never asked about these."""
    hits: list[list[int]] = []
    for pattern in control.test.get("anti_patterns", []) or []:
        hits.extend([start, end] for start, end in find_all(pattern, document)
                    if anchored(control, document, start, end))
    return hits
