"""Extraction orchestration.

One control, one model call. No batching: a control edit invalidates only its own cache
entry, and a failed call degrades one control rather than a batch. Responses are cached
under a key derived from the control's own content, the document hash and the adapter
identity, so re-running a review costs nothing and golden fixtures regenerate
deterministically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .. import jsonlogic
from ..evaluate import BAND_BY_EXPECTATION  # noqa: F401  (kept for import symmetry)
from ..loader import RegisterSet
from ..model import Control
from .base import AdapterError, ModelAdapter
from .payload import anti_pattern_hits, negative_element_results, normalize_response, verify
from .prompt import build, response_schema
from .retrieval import sweep


@dataclass
class ExtractionRun:
    payload: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: int = 0
    cache_hits: int = 0
    skipped_absent: int = 0
    truncated: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    adapter: str = ""
    # Context controls answered by the summary adapter at SUMMARY depth (ADR 0011).
    context_controls: list[str] = field(default_factory=list)
    context_calls: int = 0
    context_adapter: str = ""

    def summary(self) -> str:
        return (
            f"{len(self.payload)} controls extracted | {self.calls} model call(s), "
            f"{self.cache_hits} cached, {self.skipped_absent} resolved without a call, "
            f"{self.context_calls} context summary answer(s), "
            f"{len(self.truncated)} truncated, {len(self.failures)} failure(s)"
        )


def _cache_key(control: Control, document_sha: str, adapter_name: str) -> str:
    material = json.dumps(
        {
            "control": control.raw,
            "document": document_sha,
            "adapter": adapter_name,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def needs_extraction(control: Control, rs: RegisterSet, ctx: Mapping[str, Any]) -> bool:
    """Pre-filter so no model call is spent on a control that cannot use the answer.

    The filter is deliberately coarser than the evaluator's gating in one direction only:
    it may pass a control the evaluator later suppresses by exemption, but it must never
    suppress a control the evaluator would score from extraction. Exemption logic is not
    duplicated here precisely to keep that invariant one-sided.

    Prohibition controls are the one exception, and they are exempt in both directions:
    an inverted control is resolved entirely from the authorized-instrument set, so its
    verdict never depends on anything the model could say. Extracting for one would spend
    a call on a CRITICAL control whose answer is already determined.
    """
    if control.inverted:
        return False

    for ref in control.applicability.get("predicate_refs", []):
        if not jsonlogic.test(rs.predicates[ref]["logic"], ctx):
            return False
    classes = set(ctx.get("entity", {}).get("classes", []))
    include = control.applicability.get("include_classes", ["*"])
    exclude = control.applicability.get("exclude_classes", [])
    if classes & set(exclude):
        return False
    if "*" not in include and not classes & set(include):
        return False

    act = control.activation
    if act.get("always"):
        return True
    if "predicate_ref" in act:
        return jsonlogic.test(rs.predicates[act["predicate_ref"]]["logic"], ctx)
    if "instrument_authorized" in act:
        return act["instrument_authorized"] in (ctx.get("policy", {}).get("authorized_instruments") or [])
    if "logic" in act:
        return jsonlogic.test(act["logic"], ctx)
    return True


def run_extraction(
    rs: RegisterSet,
    adapter: ModelAdapter,
    document: str,
    entity_profile: Mapping[str, Any],
    policy_facts: Mapping[str, Any],
    cache_dir: str | Path | None = None,
    context_depth: str = "SUMMARY",
    context_adapter: ModelAdapter | None = None,
) -> ExtractionRun:
    """Produce an extraction payload for every control that could be scored.

    At SUMMARY depth a CONTEXT control is reported only as addressed or not expressly
    addressed (ADR 0011), so it is answered by `context_adapter` (the offline heuristic by
    default) and never costs a live model call. Its cache key names that adapter, so a
    later FULL run cannot mistake a summary answer for a model answer.
    """
    profile = dict(entity_profile)
    profile["classes"] = rs.expand_classes(list(profile.get("classes", [])))
    ctx = {"entity": profile, "policy": dict(policy_facts)}
    document_sha = hashlib.sha256(document.encode("utf-8")).hexdigest()

    cache_path = Path(cache_dir) if cache_dir else None
    if cache_path:
        cache_path.mkdir(parents=True, exist_ok=True)

    run = ExtractionRun(adapter=getattr(adapter, "name", "unknown"))
    if context_depth == "SUMMARY":
        if context_adapter is None:
            from .providers.heuristic import HeuristicAdapter
            context_adapter = HeuristicAdapter()
        run.context_adapter = getattr(context_adapter, "name", "unknown")

    for control in rs.controls:
        if not needs_extraction(control, rs, ctx):
            continue

        anti = anti_pattern_hits(control, document)
        found = sweep(
            document,
            list(control.test.get("search_directives", [])),
            list(control.test.get("context_directives", [])),
        )

        negatives = negative_element_results(control, document)

        if not found.matched:
            # Absence proved deterministically. No model call, and the sweep is the evidence.
            satisfied = {e.id: False for e in control.elements}
            satisfied.update(negatives["elements_satisfied"])
            run.payload[control.control_id] = {
                "elements_satisfied": satisfied,
                "spans": dict(negatives["spans"]),
                "facts": {},
                "anti_pattern_hits": anti,
                "windows_found": False,
                "retrieval_trace": found.trace + negatives["retrieval_trace"],
            }
            run.skipped_absent += 1
            continue

        summary_only = context_depth == "SUMMARY" and getattr(control, "relevance", "CORE") == "CONTEXT"
        answering = context_adapter if summary_only else adapter
        if summary_only:
            run.context_controls.append(control.control_id)
        key = _cache_key(control, document_sha, getattr(answering, "name", "unknown"))
        cached_file = cache_path / f"{key}.json" if cache_path else None
        raw: dict[str, Any] | None = None
        if cached_file and cached_file.exists():
            raw = json.loads(cached_file.read_text(encoding="utf-8"))
            run.cache_hits += 1

        if raw is None:
            prompt = build(control, found.windows)
            try:
                raw = answering.ask(prompt, control.control_id, response_schema(control))
                if summary_only:
                    run.context_calls += 1
                else:
                    run.calls += 1
            except AdapterError as exc:
                run.failures[control.control_id] = str(exc)
                run.payload[control.control_id] = {
                    "elements_satisfied": {e.id: False for e in control.elements},
                    "spans": {},
                    "facts": {},
                    "anti_pattern_hits": anti,
                    "retrieval_trace": found.trace + [f"adapter failure: {exc}"],
                }
                continue
            if cached_file:
                cached_file.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

        entry = verify(control, normalize_response(control, raw), document)
        entry["elements_satisfied"].update(negatives["elements_satisfied"])
        entry["spans"].update(negatives["spans"])
        entry["anti_pattern_hits"] = anti
        entry["windows_found"] = True
        entry["retrieval_trace"] = found.trace + entry["retrieval_trace"] + negatives["retrieval_trace"]
        if isinstance(raw, dict) and raw.get("_truncated"):
            entry["retrieval_trace"].append(
                "the provider response was truncated; complete element results were "
                "salvaged and any element that did not arrive reads as unsupported"
            )
            run.truncated.append(control.control_id)
        run.payload[control.control_id] = entry

    return run
