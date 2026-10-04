"""Measuring the register against a reviewer's own findings.

This is the instrument that turns "the pipeline runs" into "the pipeline is right", and it
is deliberately not a score. Three outputs matter, in this order:

  1. **Disagreements, itemised.** Each one is a claim the register makes that a reviewer
     did not, or the reverse. Every disagreement is adjudicated by a person and resolves
     one of three ways: the control is wrong, the reviewer was wrong, or the control is
     right but the extractor missed the evidence. Those have completely different fixes
     and the harness keeps them apart by carrying the spans and reasons into the report.
  2. **Unmapped reviewer findings.** A finding the reviewer made that no control could
     have produced is a register gap, and it is the single most valuable signal here.
     Section coverage being complete does not mean depth within a section is.
  3. **Agreement rates**, per control and overall. Useful for tracking movement between
     register versions, useless on its own for deciding whether the register is good.

Deficiency detection is scored as a detection problem rather than an exact-match problem,
because DEFICIENT versus ABSENT is a distinction reviewers rarely record consistently and
the consequential question is whether the issue was raised at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import PFIAError

# Reviewer reports use their own vocabulary. Mapping is explicit so a disagreement is
# never an artefact of two words for the same thing.
VERDICT_ALIASES = {
    "conforming": "CONFORMING", "pass": "CONFORMING", "compliant": "CONFORMING",
    "yes": "CONFORMING", "ok": "CONFORMING", "satisfied": "CONFORMING",
    "deficient": "DEFICIENT", "partial": "DEFICIENT", "fail": "DEFICIENT",
    "non-compliant": "DEFICIENT", "noncompliant": "DEFICIENT", "no": "DEFICIENT",
    "absent": "ABSENT", "not found": "ABSENT", "missing": "ABSENT", "silent": "ABSENT",
    "not applicable": "NOT_APPLICABLE", "n/a": "NOT_APPLICABLE", "na": "NOT_APPLICABLE",
    "unresolved": "APPLICABILITY_UNRESOLVED", "applicability unresolved": "APPLICABILITY_UNRESOLVED",
}
ISSUE_RAISED = {"DEFICIENT", "ABSENT"}


class GroundTruthError(PFIAError):
    """Raised when a ground-truth file cannot be reconciled with the register."""


def normalize_verdict(value: str) -> str:
    key = " ".join(str(value).strip().lower().split())
    if key in VERDICT_ALIASES:
        return VERDICT_ALIASES[key]
    upper = key.upper().replace(" ", "_")
    if upper in {"CONFORMING", "DEFICIENT", "ABSENT", "NOT_APPLICABLE", "APPLICABILITY_UNRESOLVED"}:
        return upper
    raise GroundTruthError(
        f"unrecognised reviewer verdict {value!r}; add an alias in benchmark.VERDICT_ALIASES "
        "rather than guessing what it meant"
    )


@dataclass
class Disagreement:
    control_id: str
    citation: str
    severity: str
    band: str
    reviewer: str
    model: str
    kind: str  # missed_issue | false_issue | verdict_mismatch | scope_mismatch
    model_reasons: list[str] = field(default_factory=list)
    model_spans: list[dict[str, Any]] = field(default_factory=list)
    reviewer_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id, "citation": self.citation,
            "severity": self.severity, "band": self.band, "kind": self.kind,
            "reviewer": self.reviewer, "model": self.model,
            "reviewer_note": self.reviewer_note,
            "model_reasons": self.model_reasons, "model_spans": self.model_spans,
        }


@dataclass
class CaseResult:
    case: str
    compared: int = 0
    agreed: int = 0
    disagreements: list[Disagreement] = field(default_factory=list)
    unmapped_findings: list[dict[str, Any]] = field(default_factory=list)
    unreviewed_controls: list[str] = field(default_factory=list)
    reviewer_scored_unresolved: list[str] = field(default_factory=list)
    detection: dict[str, int] = field(default_factory=dict)

    @property
    def agreement(self) -> float | None:
        return None if not self.compared else round(self.agreed / self.compared, 4)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "compared": self.compared,
            "agreed": self.agreed,
            "agreement": self.agreement,
            "detection": self.detection,
            "disagreements": [d.as_dict() for d in self.disagreements],
            "unmapped_findings": self.unmapped_findings,
            "unreviewed_controls": self.unreviewed_controls,
            "reviewer_scored_unresolved": self.reviewer_scored_unresolved,
        }


def load_ground_truth(path: str | Path) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("case", "policy", "profile", "findings"):
        if key not in document:
            raise GroundTruthError(f"{path}: ground truth is missing {key!r}")
    document["findings"] = {
        control_id: {
            "verdict": normalize_verdict(entry["verdict"] if isinstance(entry, Mapping) else entry),
            "note": entry.get("note", "") if isinstance(entry, Mapping) else "",
        }
        for control_id, entry in document["findings"].items()
    }
    return document


def compare(ledger: Mapping[str, Any], truth: Mapping[str, Any],
            known_controls: Iterable[str]) -> CaseResult:
    """Compare one ledger against one reviewer's findings."""
    result = CaseResult(case=truth["case"])
    known = set(known_controls)
    by_id = {f["control_id"]: f for f in ledger["findings"]}

    unknown = set(truth["findings"]) - known
    if unknown:
        raise GroundTruthError(
            f"{truth['case']}: ground truth references controls that are not in the register: "
            + ", ".join(sorted(unknown))
        )

    detection = {"true_positive": 0, "false_positive": 0, "false_negative": 0, "true_negative": 0}

    for control_id, entry in sorted(truth["findings"].items()):
        finding = by_id[control_id]
        model_verdict = finding["verdict"]
        reviewer_verdict = entry["verdict"]

        if model_verdict == "APPLICABILITY_UNRESOLVED":
            # Not a disagreement about the policy. The reviewer answered a question the
            # profile or the document left open, which is a data-capture gap.
            result.reviewer_scored_unresolved.append(control_id)
            continue

        result.compared += 1
        reviewer_issue = reviewer_verdict in ISSUE_RAISED
        model_issue = model_verdict in ISSUE_RAISED
        if reviewer_issue and model_issue:
            detection["true_positive"] += 1
        elif model_issue and not reviewer_issue:
            detection["false_positive"] += 1
        elif reviewer_issue and not model_issue:
            detection["false_negative"] += 1
        else:
            detection["true_negative"] += 1

        if model_verdict == reviewer_verdict:
            result.agreed += 1
            continue

        if reviewer_issue and not model_issue:
            kind = "missed_issue"
        elif model_issue and not reviewer_issue:
            kind = "false_issue"
        elif reviewer_verdict == "NOT_APPLICABLE" or model_verdict == "NOT_APPLICABLE":
            kind = "scope_mismatch"
        else:
            kind = "verdict_mismatch"

        result.disagreements.append(Disagreement(
            control_id=control_id,
            citation=finding.get("citation", ""),
            severity=finding.get("severity", ""),
            band=finding.get("band", ""),
            reviewer=reviewer_verdict,
            model=model_verdict,
            kind=kind,
            model_reasons=list(finding.get("reasons", [])),
            model_spans=[
                span
                for element in finding.get("elements", [])
                for span in element.get("spans", [])
            ][:3],
            reviewer_note=entry.get("note", ""),
        ))

    result.detection = detection
    result.unmapped_findings = list(truth.get("unmapped_findings", []))
    result.unreviewed_controls = sorted(
        control_id for control_id, finding in by_id.items()
        if control_id not in truth["findings"] and finding.get("in_scope")
    )
    return result


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    compared = sum(r.compared for r in results)
    agreed = sum(r.agreed for r in results)
    detection = {"true_positive": 0, "false_positive": 0, "false_negative": 0, "true_negative": 0}
    for result in results:
        for key, value in result.detection.items():
            detection[key] += value

    tp, fp, fn = detection["true_positive"], detection["false_positive"], detection["false_negative"]
    precision = round(tp / (tp + fp), 4) if (tp + fp) else None
    recall = round(tp / (tp + fn), 4) if (tp + fn) else None

    by_control: dict[str, dict[str, int]] = {}
    for result in results:
        for disagreement in result.disagreements:
            entry = by_control.setdefault(disagreement.control_id, {})
            entry[disagreement.kind] = entry.get(disagreement.kind, 0) + 1

    return {
        "cases": len(results),
        "compared": compared,
        "agreed": agreed,
        "agreement": round(agreed / compared, 4) if compared else None,
        "detection": detection,
        "precision": precision,
        "recall": recall,
        "controls_with_disagreements": dict(
            sorted(by_control.items(), key=lambda kv: -sum(kv[1].values()))
        ),
        "unmapped_finding_count": sum(len(r.unmapped_findings) for r in results),
        "note": (
            "Precision and recall treat DEFICIENT and ABSENT as an issue raised. They "
            "measure whether the pipeline surfaces what a reviewer surfaces, not whether "
            "the register is a correct reading of the statute. Unmapped reviewer findings "
            "measure that, and they are the number to act on first."
        ),
    }
