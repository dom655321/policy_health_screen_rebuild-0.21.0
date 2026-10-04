"""Client-facing phrasing.

The register's own vocabulary - CONFORMING, DEFICIENT, ABSENT, critical failure - is audit
vocabulary, and audit vocabulary carries a claim this tool is not in a position to make. In
public finance, "failure" and "deficiency" read as a breach of fiduciary duty. A board
member seeing "STATUTORY DEFICIENCY PRESENT" hears an accusation about the entity's conduct.

What the tool actually observes is narrower and more defensible: **whether a provision of
the subchapter is expressly addressed in the text of the policy document.** It does not
observe what the entity does, whether anyone breached a duty, or whether the entity is out
of compliance. Relocating the claim from the entity's conduct to the document's text is not
softening - it is the accurate statement of what was examined, which is why it should also
be the easier one to clear with compliance.

Three rules govern this vocabulary:

1. **Describe the document, not the entity.** "Not expressly addressed" rather than
   "failure". The subject of every client-facing sentence is the policy text.
2. **Never assert a legal conclusion.** No "non-compliant", "violation", "deficiency",
   "breach", "failure". Those are determinations a licensed professional makes on a full
   record, and this screen has neither.
3. **Keep the substance.** A mandatory provision that the policy does not address is still
   reported, still ranked first, and still named as mandatory. Nothing is hidden; the
   sentence simply says what was found rather than what it implies.

The internal vocabulary is deliberately unchanged. Reviewers adjudicating a finding need
the evaluator's own terms, and the ledger is the artifact of record.
"""

from __future__ import annotations

from typing import Any, Mapping

# Register verdict -> what a client-facing page says about the policy text.
STATUS_PHRASING = {
    "CONFORMING": "Addressed",
    "ABSENT": "Not expressly addressed",
    "NOT_APPLICABLE": "Not applicable",
    "APPLICABILITY_UNRESOLVED": "Confirmation required",
}
PARTIAL = "Addressed in part"
# A figure or term the policy states that sits outside the statutory limit. Worth its own
# phrasing: "not addressed" would be wrong, because the policy did address it.
DIFFERING = "Stated terms differ from the statute"

# Severity -> the priority a reader should give it. "Critical" reads as an incident.
SEVERITY_PHRASING = {
    "CRITICAL": "Mandatory",
    "HIGH": "Significant",
    "MEDIUM": "Moderate",
    "ADVISORY": "Practice",
    "Critical": "Mandatory",
    "High": "Significant",
    "Moderate": "Moderate",
    "Enhancement": "Practice",
}

# Section status (ADR 0010). Set by fixed rules on the items beneath it; never a number.
SECTION_PHRASING = {
    "REVISIONS_RECOMMENDED": "Revisions recommended",
    "ADDITIONS_RECOMMENDED": "Additions recommended",
    "ADDRESSES_PROVISIONS_REVIEWED": "Addresses the provisions reviewed",
    "REVIEW_IN_PROGRESS": "Review in progress",
    "NOT_ASSESSED": "Not assessed",
    "SUMMARIZED": "Summarized, not reviewed in detail",
    "PAUSED": "Paused",
}
SECTION_LABELS = {
    "AUTHORIZED_INVESTMENTS": "Authorized investments",
    "PFIA_REQUIREMENTS": "Investment management provisions",
    "POLICY_GOVERNANCE": "Policy governance (summary)",
    "GTOT": "GTOT certification criteria",
}
# Item status -> what a client-facing page says about the policy text.
ITEM_PHRASING = {
    "ALIGNED": "Addressed",
    "ALIGNED_BY_REFERENCE": "Addressed by reference to the Act",
    "PARTIALLY_ADDRESSED": "Addressed in part",
    "NOT_ADDRESSED": "Not expressly addressed",
    "NOT_APPLICABLE": "Not applicable",
    "REVIEW_REQUIRED": "Confirmation required",
}

# Titles are kept short enough to set on one or two lines, and forward-looking rather than
# retrospective: what to do next, not what went wrong. The annual review required by
# Sec. 2256.005(e) is the natural occasion for an amendment, so the subtitle points at it.
VERDICTS = {
    "revisions": (
        "AMENDMENTS RECOMMENDED",
        "Stated terms differ from the Act and should be aligned with it",
    ),
    "additions": (
        "AMENDMENTS RECOMMENDED",
        "Required provisions are not expressly addressed in the policy text",
    ),
    "consideration": (
        "ITEMS FOR CONSIDERATION",
        "No mandatory provision was found unaddressed",
    ),
    "aligned": (
        "NO ITEMS IDENTIFIED",
        "Every provision applicable to this entity is expressly addressed",
    ),
    "blocked": (
        "REVIEW INCOMPLETE",
        "Confirmation required before a result can be stated",
    ),
}

GATE_NOTE = (
    "This result is set by fixed rules on the items beneath it: a stated term that differs "
    "from the Act first, then a required provision not expressly addressed. No score or "
    "weighting is applied."
)


def status(item_status: str) -> str:
    """Phrase an item status for a client-facing page."""
    if item_status == "CONFLICTS":
        return DIFFERING
    return ITEM_PHRASING.get(item_status, item_status)


def section(section_status: str) -> str:
    return SECTION_PHRASING.get(section_status, section_status)


def severity(value: str) -> str:
    return SEVERITY_PHRASING.get(value, value)


def verdict(overall: str, blocked: bool) -> tuple[str, str]:
    """Cover verdict from the section statuses (ADR 0010)."""
    if blocked or overall == "REVIEW_IN_PROGRESS":
        return VERDICTS["blocked"]
    if overall == "REVISIONS_RECOMMENDED":
        return VERDICTS["revisions"]
    if overall == "ADDITIONS_RECOMMENDED":
        return VERDICTS["additions"]
    return VERDICTS["aligned"]


def summary(reviewed: int, addressed: int, mandatory_open: int, advisory_reviewed: int) -> str:
    """The executive summary, written as an observation about the document.

    Deliberately counts what is addressed first. The same figures in the other order read as
    a tally of faults, and the tool has no basis for calling anything a fault.
    """
    scored, advisory_scored = reviewed, advisory_reviewed
    open_items = scored - addressed
    parts = [
        f"This screen compared the policy text against {scored} provision(s) of Tex. Gov't "
        f"Code ch. 2256, Subchapter A applicable to this entity."
    ]
    if not scored:
        return (
            "No provision of the subchapter could be reviewed against this policy. The result "
            "is inconclusive rather than favourable; see the confirmation items below."
        )
    parts.append(f"{addressed} are expressly addressed in the policy.")
    if open_items:
        sentence = (
            f"{open_items} are not addressed, or are addressed in part"
        )
        if mandatory_open:
            sentence += (
                f", of which {mandatory_open} relate to mandatory provisions and are "
                "recommended for amendment at the next annual review"
            )
        parts.append(sentence + ".")
    if advisory_scored:
        parts.append(
            f"A further {advisory_scored} item(s) concern provisions the Act binds whether or not the policy restates them "
            "and are reported separately."
        )
    parts.append(
        "This screen reads the policy document only. It does not examine the entity's "
        "investment practices, holdings or management controls, and it is not a "
        "determination of compliance."
    )
    return " ".join(parts)


def priority_lede() -> str:
    return (
        "Provisions of the subchapter that the policy text does not expressly address, or "
        "addresses in part, ordered by the priority a reader should give them. Each is an "
        "item for consideration rather than a determination."
    )


def forbidden_terms() -> tuple[str, ...]:
    """Words a client-facing page must not contain.

    Each asserts a legal conclusion, a breach of duty, or an audit finding. The screen
    supports none of the three, and a page that uses them invites a defensive reading of an
    observation about drafting.
    """
    return (
        "deficiency", "deficient", "failure", "failed", "fail",
        "violation", "violates", "non-compliant", "noncompliant", "breach",
        "contradicted", "critical",
    )


def scrub_check(text: str) -> list[str]:
    """Return any forbidden term present in `text`, for use in tests and CI."""
    lowered = text.lower()
    return [term for term in forbidden_terms() if term in lowered]


def phrase_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Client-facing view of one finding: section, requirement, priority, status."""
    return {
        "section": finding["citation"],
        "title": finding["title"],
        "severity": severity(finding["severity"]),
        "status": status(finding.get("status", "")),
    }
