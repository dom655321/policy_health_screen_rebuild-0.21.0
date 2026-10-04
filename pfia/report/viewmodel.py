"""Ledger to report view model.

The template inherited from the earlier build speaks a different vocabulary from this
register, so the mapping is made explicit here rather than being smuggled into the
template. Two rules govern it:

  * every mapping is lossless in the direction that matters - a reader must be able to
    recover what the evaluator actually decided;
  * anything this pipeline does not produce is rendered as "not performed", never as a
    plausible default. A blank governance index or an empty certification table that reads
    as "all clear" is the single most dangerous thing a compliance report can do.

Nothing here calls a model. The view model is a pure function of the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping

# Item status (ADR 0010) -> the internal template's vocabulary. A conflict and a partial
# are distinct statuses in the evaluator, so nothing is inferred from a number here.
STATUS_BY_ITEM = {
    "ALIGNED": "Pass",
    "ALIGNED_BY_REFERENCE": "Pass",
    "PARTIALLY_ADDRESSED": "Partial",
    "CONFLICTS": "Fail",
    "NOT_ADDRESSED": "Not Found",
    "NOT_APPLICABLE": "Not Applicable",
    "REVIEW_REQUIRED": "Applicability Unresolved",
}
# Worst first; the cover reads the worst section status.
SECTION_ORDER = ("REVIEW_IN_PROGRESS", "REVISIONS_RECOMMENDED", "ADDITIONS_RECOMMENDED",
                 "ADDRESSES_PROVISIONS_REVIEWED", "NOT_ASSESSED")
SEVERITY_MAP = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Moderate",
    "ADVISORY": "Enhancement",
}
from . import phrasing  # noqa: E402  client-facing vocabulary, kept in one place

REQUIREMENT_CLASS = {
    "MANDATORY_CONTENT": "MANDATORY",
    "MANDATORY_CONDUCT": "MANDATORY",
    "PROHIBITION": "PROHIBITION",
    "PERMISSIVE_ENABLING_WITH_CONDITIONS": "CONDITIONAL",
    "DEFINITIONAL": "DEFINITIONAL",
}


class Enum:
    """Minimal stand-in for the template's `.value` accessor on enum fields."""

    __slots__ = ("value",)

    def __init__(self, value: str):
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Enum) and other.value == self.value

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Enum({self.value!r})"


@dataclass
class ElementView:
    citation: str
    requirement: str
    status: Enum
    critical: bool = False


@dataclass
class FindingView:
    control_id: str
    band: str
    section: str
    title: str
    framework: Enum
    requirement_class: Enum
    status: Enum
    severity: Enum
    confidence: Enum
    display_status: str
    rubric_citation: str
    evidence: str
    analysis: str
    raw_quote: str = ""
    recommendation: str = ""
    review_limitations: str = ""
    remediation_error: bool = False
    model_status: Enum | None = None
    elements: list[ElementView] = field(default_factory=list)


@dataclass
class Provenance:
    source_filename: str
    source_sha256: str
    policy_version: str | None
    entity_class_label: str | None
    entity_class_register_status: str
    generated_at: datetime
    extraction_model: str
    critic_model: str
    remediation_model: str | None
    critic_status: str
    revision_count: int
    kb_banner: str
    register_version: str
    source_text_coverage: str
    prompt_version: str
    schema_version: str


@dataclass
class ReportView:
    entity_name: str
    review_date: date
    statutory_verdict: Enum
    mandatory_partial_count: int
    statutory_findings: list[FindingView]
    gtot_findings: list[FindingView]
    hsam_findings: list[FindingView]
    quality_scores: list[Any]
    provenance: Provenance
    blocking_reasons: list[str]
    applicability_review_required: list[str]
    unverified_quotes: list[str]
    citations_validated: bool
    blocked_templates: list[str]
    executive_summary_text: str
    priority_action_text: str
    internal_use_notice: str
    required_disclosures: list[str]
    hsam_constraint: str
    element_mode: bool
    element_control_count: int

    @property
    def is_conclusion_blocked(self) -> bool:
        return self.statutory_verdict.value == "Conclusion Blocked"


def _status_for(finding: Mapping[str, Any]) -> str:
    return STATUS_BY_ITEM.get(finding.get("status", ""), "Applicability Unresolved")


def _confidence_for(finding: Mapping[str, Any], extractor: str) -> str:
    """Confidence is about the evidence, not about the conclusion.

    A verdict resting on verified spans is High. Discarded claims, or an extractor that
    cannot test an element assertion at all, drop it.
    """
    if finding.get("discarded_claims"):
        return "Low"
    if extractor.startswith("heuristic") or extractor.startswith("keyword"):
        return "Low"
    if finding["verdict"] == "NOT_APPLICABLE":
        return "High"
    has_spans = any(element.get("spans") for element in finding.get("elements", []))
    return "High" if has_spans or finding["verdict"] == "ABSENT" else "Moderate"


def _evidence_for(finding: Mapping[str, Any]) -> tuple[str, str]:
    """Return the evidence block and the raw quote it came from."""
    for element in finding.get("elements", []):
        for span in element.get("spans", []):
            text = " ".join(str(span.get("text", "")).split())
            if text:
                page = span.get("page")
                where = f" (page {page})" if page else f" (offset {span.get('start')})"
                return f"\u201c{text}\u201d{where}", text
    hits = finding.get("anti_pattern_hits", [])
    if hits:
        text = " ".join(str(hits[0].get("text", "")).split())
        page = hits[0].get("page")
        where = f" (page {page})" if page else ""
        return (
            f"Non-conforming language located{where}: \u201c{text}\u201d",
            text,
        )
    return ("No supporting language located in the policy text.", "")


REVIEW_ACTION_LABEL = {
    "VERIFY_EXTRACTION": "Reviewer action: verify the extraction before treating this as a "
                         "policy gap.",
    "CONFIRM_ABSENCE": "Reviewer action: confirm the policy is genuinely silent on this "
                       "subject.",
    "READ_THE_PASSAGE": "Reviewer action: read the flagged passage; this is either a defect "
                        "or a phrase used differently.",
    "INTERPRETIVE": "Reviewer action: a judgment call on contested text, not a lookup.",
    "REVIEW_FINDING": "Reviewer action: ordinary review against the located evidence.",
}


def _analysis_for(finding: Mapping[str, Any]) -> str:
    """Compose the analysis deterministically from the register and the evaluation.

    Deliberately not model prose. Every sentence here is traceable to a control field or
    to a decision the evaluator recorded, which is what lets the report be defended line
    by line.
    """
    parts = [finding["title"] + "."]
    unsatisfied = [e["assertion"] for e in finding.get("elements", []) if not e.get("satisfied")]
    if unsatisfied:
        parts.append(
            f"{len(unsatisfied)} of {len(finding['elements'])} statutory elements were not "
            "satisfied by the policy text: " + " ".join(f"({i + 1}) {a}" for i, a in enumerate(unsatisfied))
        )
    if finding.get("anti_pattern_hits"):
        parts.append(
            f"{len(finding['anti_pattern_hits'])} passage(s) matched language known to defeat "
            "this requirement."
        )
    for reason in finding.get("reasons", []):
        parts.append(reason[0].upper() + reason[1:] + ("" if reason.endswith(".") else "."))
    label = REVIEW_ACTION_LABEL.get(finding.get("review_action", ""))
    if label:
        parts.append(label)
    return " ".join(parts)


def _limitations_for(finding: Mapping[str, Any], extractor: str) -> str:
    notes: list[str] = []
    for claim in finding.get("discarded_claims", []):
        if claim.get("reason") == "quote_not_in_document":
            notes.append(
                f"A supporting quotation offered for element {claim['element_id']} could not be "
                "located in the document and was discarded."
            )
        else:
            notes.append(f"Element {claim['element_id']} was asserted without a citation and was discarded.")
    if extractor.startswith("heuristic") or extractor.startswith("keyword"):
        notes.append(
            "Extraction ran on a deterministic keyword stand-in rather than a language model. "
            "Element-level conclusions are indicative only and are not review-grade."
        )
    return " ".join(notes)


SEVERITY_RANK = {"Critical": 0, "High": 1, "Moderate": 2, "Enhancement": 3, "Unrated": 4}


def build(ledger: Mapping[str, Any], entity_name: str, *, policy_version: str | None = None,
          entity_class_label: str | None = None) -> dict[str, Any]:
    """Build the full template context from a finding ledger."""
    severity_rank = SEVERITY_RANK
    findings = ledger["findings"]
    extractor = ledger.get("extractor", "unknown")
    document = ledger.get("document", {})
    sections = ledger["sections"]

    statutory_views: list[FindingView] = []
    advisory_views: list[FindingView] = []
    unverified: list[str] = []
    unresolved: list[str] = []

    for finding in findings:
        status = _status_for(finding)
        evidence, raw_quote = _evidence_for(finding)
        view = FindingView(
            control_id=finding["control_id"],
            band=finding.get("band", "STATUTORY"),
            section=finding["citation"],
            title=finding["title"],
            framework=Enum("PFIA"),
            requirement_class=Enum(REQUIREMENT_CLASS.get(finding.get("normative_force", ""), "CONDITIONAL")),
            status=Enum(status),
            severity=Enum(SEVERITY_MAP.get(finding["severity"], "Unrated")),
            confidence=Enum(_confidence_for(finding, extractor)),
            display_status=status,
            rubric_citation=f"Tex. Gov't Code {finding['citation']}",
            evidence=evidence,
            raw_quote=raw_quote,
            analysis=_analysis_for(finding),
            review_limitations=_limitations_for(finding, extractor),
            recommendation=finding.get("remediation_language", ""),
            elements=[
                ElementView(
                    citation=f"{finding['citation']} el. {element['element_id']}",
                    requirement=element["assertion"],
                    status=Enum("Pass" if element.get("satisfied") else "Fail"),
                )
                for element in finding.get("elements", [])
            ],
        )
        for claim in finding.get("discarded_claims", []):
            unverified.append(f"{finding['control_id']}:{claim['element_id']}")
        if finding["verdict"] == "APPLICABILITY_UNRESOLVED":
            unresolved.append(finding["control_id"])

        (advisory_views if finding.get("band") == "ADVISORY" else statutory_views).append(view)

    in_scope_statutory = [f for f in findings if f.get("band") != "ADVISORY" and f.get("in_scope")]
    in_scope_advisory = [f for f in findings if f.get("band") == "ADVISORY" and f.get("in_scope")]
    passed = sum(1 for f in in_scope_statutory if f.get("status") in ("ALIGNED", "ALIGNED_BY_REFERENCE"))
    pfia, instruments_section = sections["PFIA_REQUIREMENTS"], sections["AUTHORIZED_INVESTMENTS"]
    open_items = sorted(set(pfia["conflicts"] + pfia["additions"]
                            + instruments_section["conflicts"] + instruments_section["additions"]))
    partials = sum(
        1 for f in in_scope_statutory
        if f.get("status") == "PARTIALLY_ADDRESSED"
        and REQUIREMENT_CLASS.get(f.get("normative_force", "")) == "MANDATORY"
    )
    overall = min((pfia["status"], instruments_section["status"]), key=SECTION_ORDER.index)

    # Blocking comes first. A verdict reached over a partly unresolved applicable set is
    # a verdict the reviewer never made.
    blocking: list[str] = []
    if not in_scope_statutory:
        blocking.append(
            "No statutory control could be reviewed. Either the entity profile is unanswered "
            "or the entity falls outside Subchapter A."
        )
    quality_block = (document.get("quality") or {})
    if quality_block.get("verdict") not in (None, "OK"):
        blocking.append(
            f"Text extraction quality is {quality_block['verdict']}: "
            + "; ".join(quality_block.get("reasons", []))[:400]
            + " Findings of absence cannot be distinguished from extraction gaps."
        )
    instruments = ledger.get("instruments") or {}
    if instruments.get("unresolved"):
        blocking.append(
            "The policy's authorized-investment set could not be established from the "
            f"document ({instruments.get('state')}), so the instrument controls are "
            "undetermined."
        )
    profile_block = ledger.get("profile") or {}
    mandatory_unresolved = [
        f["control_id"] for f in findings
        if f["verdict"] == "APPLICABILITY_UNRESOLVED"
        and REQUIREMENT_CLASS.get(f.get("normative_force", "")) == "MANDATORY"
    ]
    if mandatory_unresolved:
        blocking.append(
            f"{len(mandatory_unresolved)} mandatory control(s) could not be resolved from the "
            "entity profile: " + ", ".join(mandatory_unresolved[:8])
            + ("..." if len(mandatory_unresolved) > 8 else "")
        )

    client_verdict, client_subtitle = phrasing.verdict(overall, blocked=bool(blocking))

    if blocking:
        verdict = "Conclusion Blocked"
    elif overall == "REVISIONS_RECOMMENDED":
        verdict = "Revisions Recommended"
    elif overall == "ADDITIONS_RECOMMENDED":
        verdict = "Additions Recommended"
    else:
        verdict = "Clear"

    quality = document.get("quality") or {}
    blocked_templates = [] if not unverified else ["TMPL-001"]

    report = ReportView(
        entity_name=entity_name,
        review_date=date.today(),
        statutory_verdict=Enum(verdict),
        mandatory_partial_count=partials,
        statutory_findings=statutory_views,
        gtot_findings=[],
        hsam_findings=advisory_views,
        quality_scores=[],
        blocking_reasons=blocking,
        applicability_review_required=unresolved,
        unverified_quotes=unverified,
        citations_validated=not unverified,
        blocked_templates=blocked_templates,
        executive_summary_text=(
            f"{len(in_scope_statutory)} statutory control(s) were reviewed against the policy "
            f"text. {passed} are addressed and {len(open_items)} carry an item for action. "
            f"PFIA requirements: {phrasing.section(pfia['status'])}. Authorized investments: "
            f"{phrasing.section(instruments_section['status'])}. This screen reads the policy "
            "document only; it does not test what the entity actually does."
        ),
        priority_action_text=(
            "Address stated conflicts with the Act first, then required provisions not "
            "addressed: " + ", ".join(open_items)
            if open_items else "No statutory item for action was identified in the controls reviewed."
        ),
        internal_use_notice=(
            "Findings are generated from a machine-readable control register and verified span "
            "extraction. They have not been reviewed by a licensed professional."
        ),
        required_disclosures=[
            "This screen evaluates policy text against Tex. Gov't Code ch. 2256 and does not "
            "constitute legal advice",
            "Controls absent from the register are not evaluated and their absence is not a "
            "finding of compliance",
        ],
        hsam_constraint="the Public Funds Investment Act as a requirement of the policy text",
        element_mode=True,
        element_control_count=sum(1 for f in findings if f.get("elements")),
        provenance=Provenance(
            source_filename=document.get("label", "unknown"),
            source_sha256=document.get("source_sha256") or document.get("sha256", ""),
            policy_version=policy_version,
            entity_class_label=entity_class_label,
            entity_class_register_status="loaded",
            generated_at=datetime.now(timezone.utc),
            extraction_model=extractor,
            critic_model="deterministic span verification; no model critic in this pipeline",
            remediation_model=None,
            # "approved" here means every quotation offered by the extractor was located
            # in the document. That is a stronger claim than a model critic makes, and it
            # is what suppresses the verification banner in the template.
            critic_status="unverified" if unverified else "approved",
            revision_count=0,
            kb_banner="statutory control register only; no external knowledge base consulted",
            register_version=", ".join(
                f"{r['schedule']}@{r['version']}" for r in ledger.get("registers", [])
            ),
            source_text_coverage=(
                f"{document.get('backend', 'unknown')} backend, {document.get('pages', '?')} "
                f"page(s), extraction quality {quality.get('verdict', 'n/a')}"
                + (f", {quality.get('skipped_streams')} undecoded content stream(s)"
                   if quality.get("skipped_streams") else "")
            ),
            prompt_version="register-derived; no standalone prompt artifact",
            schema_version="register.schema.json 2020-12",
        ),
    )

    deficiencies = sorted(
        (v for v in statutory_views + advisory_views
         if v.status.value in ("Fail", "Partial", "Not Found")),
        key=lambda v: (severity_rank.get(v.severity.value, 9), v.control_id),
    )

    coverage_block = ledger.get("coverage") or {}
    unresolved_block = ledger.get("unresolved") or []
    instruments_block = ledger.get("instruments") or {}
    queue = ledger.get("review_queue") or []
    action_text = ledger.get("review_actions") or {}

    by_action: dict[str, list[dict[str, Any]]] = {}
    for item in queue:
        by_action.setdefault(item["review_action"], []).append(item)

    severity_rank_q = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "ADVISORY": 3}
    for items in by_action.values():
        items.sort(key=lambda i: (severity_rank_q.get(i["severity"], 9), i["control_id"]))

    return {
        "report": report,
        "distribution": "internal",
        # Everything below is internal-section material. Page one is built only from the
        # client_safe block, so nothing here can leak into a page intended for
        # distribution by accident.
        "coverage": coverage_block,
        "unresolved": unresolved_block,
        "instruments": instruments_block,
        "review_queue": queue,
        "review_by_action": by_action,
        "review_action_text": action_text,
        "sections": sections,
        "section_labels": {k: phrasing.section(v["status"]) for k, v in sections.items()},
        "client_safe": {
            "entity_name": entity_name,
            "entity_class": entity_class_label,
            "policy_version": policy_version,
            "review_date": report.review_date,
            # Client-facing wording comes from phrasing.py and nowhere else. The register's
            # own vocabulary is audit vocabulary and carries a claim about the entity's
            # conduct that this screen is not in a position to make.
            "section_status": {k: phrasing.section(v["status"]) for k, v in sections.items()},
            "section_list": [{"label": phrasing.SECTION_LABELS[k], "status": phrasing.section(v["status"])}
                             for k, v in sections.items()],
            "scope_statement": ("Governance and administrative provisions are summarized, not "
                                "reviewed in detail."),
            "verdict": client_verdict,
            "verdict_subtitle": client_subtitle,
            "gate_note": phrasing.GATE_NOTE,
            "summary": phrasing.summary(
                len(in_scope_statutory), passed, len(open_items), len(in_scope_advisory),
            ),
            "priority_lede": phrasing.priority_lede(),
            "statutory_passed": passed,
            "statutory_reviewed": len(in_scope_statutory),
            "advisory_reviewed": len(in_scope_advisory),
            "controls_total": len(findings),
            "controls_reviewed": len(in_scope_statutory) + len(in_scope_advisory),
            "unresolved_count": len(unresolved_block),
            "coverage_statement": coverage_block.get("statement", ""),
            "sections_covered": coverage_block.get("sections_covered"),
            "sections_testable": coverage_block.get("sections_testable"),
            # Section and title only. No control identifiers, no draft language, no
            # confidence labels: those are internal artifacts and a client page that
            # carried them would be describing the tool rather than the policy.
            "priority": [
                phrasing.phrase_finding(f)
                for f in sorted(
                    (f for f in findings
                     if f.get("band") != "ADVISORY"
                     and f.get("in_scope")
                     and f.get("status") in ("CONFLICTS", "NOT_ADDRESSED", "PARTIALLY_ADDRESSED")),
                    key=lambda f: (f.get("status") != "CONFLICTS", severity_rank.get(
                        SEVERITY_MAP.get(f["severity"], "Unrated"), 9), f["control_id"]),
                )
            ][:12],
            "blocking": blocking,
            "disclosures": report.required_disclosures,
        },
        "doc_id": ledger.get("ledger_sha256", "")[:16].upper(),
        "overall_status": overall,
        "overall_label": phrasing.section(overall),
        "all_controls": len(findings),
        "scorecard": _scorecard(findings),
        "statutory": {"passed": passed, "reviewed": len(in_scope_statutory)},
        "gtot": {"status": sections.get("GTOT", {}).get("status", "PAUSED"),
                 "label": phrasing.section(sections.get("GTOT", {}).get("status", "PAUSED")),
                 "reviewed": len([f for f in findings if f.get("section") == "GTOT" and f.get("in_scope")])},
        "deficiencies": deficiencies,
        "deficiency_count": len(deficiencies),
    }


COLOURS = {
    "Pass": "#15803D", "Partial": "#C2410C", "Fail": "#BE123C",
    "Not Found": "#BE123C", "Not Applicable": "#D4D4D8",
}


def _scorecard(findings: list[Mapping[str, Any]]) -> str:
    """Render the control grid as inline HTML, one cell per control."""
    cells = []
    for finding in findings:
        status = _status_for(finding)
        colour = COLOURS.get(status, "#A16207")
        cells.append(
            f'<span title="{finding["control_id"]}" style="display:inline-block;width:9px;'
            f'height:9px;margin:1px;background:{colour};"></span>'
        )
    return '<div style="line-height:0;">' + "".join(cells) + "</div>"
