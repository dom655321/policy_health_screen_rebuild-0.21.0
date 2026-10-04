"""Finding ledger: the signed artifact the PDF report renders from.

The report is a projection of this document. Nothing in the report may assert
anything the ledger does not contain, and the ledger is content-addressed so a
report can be tied back to the exact register version, document and extractor that
produced it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .evaluate import ReviewResult
from .jsonlogic import UNKNOWN
from .ingest import SourceDocument
from .loader import RegisterSet


def _plain(obj: Any) -> Any:
    if obj is UNKNOWN:
        # Serialized as a string rather than null so a reader can tell an unanswered
        # question from a question answered "none".
        return "UNKNOWN"
    if is_dataclass(obj):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    return obj


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _annotate_pages(findings: list[dict[str, Any]], source: SourceDocument) -> None:
    """Resolve every span offset to a source page.

    A board reads page numbers, not character offsets. The offsets stay in the ledger
    because they are what the span verification actually proved; the page is the
    human-facing projection of the same fact.
    """
    def annotate(span: dict[str, Any]) -> None:
        page = source.page_for(span.get("start", 0))
        if page is not None:
            span["page"] = page

    for finding in findings:
        for element in finding.get("elements", []):
            for span in element.get("spans", []):
                annotate(span)
        for span in finding.get("anti_pattern_hits", []):
            annotate(span)


def build_ledger(
    rs: RegisterSet,
    result: ReviewResult,
    document: str,
    document_label: str,
    extractor_name: str,
    source: SourceDocument | None = None,
    coverage: Any | None = None,
    profile_report: Any | None = None,
    instruments: Any | None = None,
    instrument_conditions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    findings = [_plain(f) for f in result.findings]
    # in_scope and part are properties, so asdict() drops them. Downstream consumers need
    # them without re-deriving the gating rules.
    for entry, finding in zip(findings, result.findings):
        entry["in_scope"] = finding.in_scope
        entry["part"] = finding.part
        entry["relevance"] = rs.control(finding.control_id).relevance
    if source is not None:
        _annotate_pages(findings, source)

    document_block: dict[str, Any] = {
        "label": document_label,
        "sha256": sha256_text(document),
        "chars": len(document),
    }
    if source is not None:
        document_block.update(source.provenance())
        document_block["label"] = document_label

    from . import __version__

    body: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_version": __version__,
        "document": document_block,
        "extractor": extractor_name,
        "registers": [
            {
                "id": r.id,
                "schedule": r.schedule,
                "version": r.version,
                "law_in_force_as_of": r.law_in_force_as_of,
                "canonical_source": r.canonical_source,
                "control_count": len(r.controls),
            }
            for r in rs.registers
        ],
        "entity_profile": _plain(result.context["entity"]),
        "policy_facts": _plain(result.context["policy"]),
        # Categorical (ADR 0010): a status per section by fixed rules, and counts of item
        # statuses. There is no index, weight or composite anywhere in the ledger.
        "sections": result.sections(),
        "in_scope_controls": len(result.in_scope()),
        "total_controls": len(result.findings),
        "unresolved_controls": len(result.unresolved()),
        # Three things a reader would otherwise have to assume. Each is the difference
        # between a determination and the absence of one.
        "unresolved": [
            {
                "control_id": f.control_id,
                "citation": f.citation,
                "severity": f.severity,
                "reasons": f.reasons,
                "unanswered_facts": f.unanswered_facts,
            }
            for f in result.unresolved()
        ],
        "review_actions": {
            key: text for key, text in __import__(
                "pfia.evaluate", fromlist=["REVIEW_ACTIONS"]
            ).REVIEW_ACTIONS.items() if text
        },
        "review_queue": _plain([
            {"control_id": f.control_id, "citation": f.citation, "severity": f.severity,
             "section": f.section, "band": f.band, "status": f.status, "verdict": f.verdict,
             "review_action": f.review_action}
            for f in sorted(result.in_scope(), key=lambda x: x.control_id)
            if f.review_action and f.review_action != "NONE"
        ]),
        "coverage": coverage.to_dict() if coverage is not None else None,
        "profile": None if profile_report is None else {
            "answered": list(profile_report.answered),
            "unanswered": list(profile_report.unanswered),
            "blocked_controls": dict(profile_report.blocked_controls),
            "complete": profile_report.complete,
        },
        "instruments": instruments.report() if instruments is not None else None,
        "findings": findings,
    }
    if instrument_conditions is not None:
        # Schedule B v2 parallel run (ADR 0009). Proposed: reported, never sets a status.
        body["instrument_conditions"] = dict(instrument_conditions)
    body["ledger_sha256"] = sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":")))
    return body


def write_ledger(path: str, ledger: Mapping[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
