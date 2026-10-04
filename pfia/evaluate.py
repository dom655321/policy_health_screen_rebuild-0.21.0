"""Deterministic verdict and status derivation (categorical; ADR 0010).

Pipeline per control:
    register gate -> control applicability -> exemptions -> activation -> elements

Every stage that stops evaluation records a machine-readable reason, so a
NOT_APPLICABLE finding is as defensible as a DEFICIENT one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from . import jsonlogic
from .jsonlogic import UNKNOWN
from .extraction import ControlExtraction, Extractor, Span


def _find_literal(phrase: str, document: str) -> list[tuple[int, int]]:
    """Whitespace-tolerant literal search, shared with the retrieval layer."""
    from .adapter.retrieval import find_all

    return find_all(phrase, document)
from .loader import RegisterSet
from .model import SEVERITY_ORDER, Control

CONFORMING = "CONFORMING"
DEFICIENT = "DEFICIENT"
ABSENT = "ABSENT"
NOT_APPLICABLE = "NOT_APPLICABLE"
# A control whose applicability turns on a fact the reviewer has not supplied. Distinct
# from NOT_APPLICABLE, which is a determination; this is the absence of one. Both are
# out of scope for a section status, but only one of them is an answer.
APPLICABILITY_UNRESOLVED = "APPLICABILITY_UNRESOLVED"

STATUTORY = "STATUTORY"
ADVISORY = "ADVISORY"

# Band is derived from where the obligation lives, not from how important it is.
#   REQUIRED               the statute requires the policy itself to contain it
#   RECOMMENDED            the statute ties the duty to the policy by reference
#   RECOMMENDED_NOT_REQUIRED   the duty exists independently of the policy
# Only the first two can produce a statutory finding. Band is resolved per element
# (ADR 0010): an element may sit in a different band from its control.
BAND_BY_EXPECTATION = {
    "REQUIRED": STATUTORY,
    "RECOMMENDED": STATUTORY,
    "RECOMMENDED_NOT_REQUIRED": ADVISORY,
}

# Item status: what the policy text does with a requirement. No weights, no fractions.
ALIGNED = "ALIGNED"
ALIGNED_BY_REFERENCE = "ALIGNED_BY_REFERENCE"
PARTIALLY_ADDRESSED = "PARTIALLY_ADDRESSED"
NOT_ADDRESSED = "NOT_ADDRESSED"
CONFLICTS = "CONFLICTS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUSES = (CONFLICTS, NOT_ADDRESSED, PARTIALLY_ADDRESSED, REVIEW_REQUIRED,
            ALIGNED_BY_REFERENCE, ALIGNED, NOT_APPLICABLE)

# Report sections, routed by authority then schedule; the part within a section by band.
PFIA_REQUIREMENTS = "PFIA_REQUIREMENTS"
AUTHORIZED_INVESTMENTS = "AUTHORIZED_INVESTMENTS"
GTOT = "GTOT"
POLICY_GOVERNANCE = "POLICY_GOVERNANCE"
# Output order (ADR 0011): the firm's business first. GTOT appears only when a GTOT register
# is loaded; it is paused in this release.
SECTIONS = (AUTHORIZED_INVESTMENTS, PFIA_REQUIREMENTS, POLICY_GOVERNANCE, GTOT)
# Context depth (ADR 0011). SUMMARY: a CONTEXT control is one addressed / not addressed line
# in the policy governance summary. FULL: every control is reviewed element by element.
SUMMARY, FULL = "SUMMARY", "FULL"
SUMMARIZED = "SUMMARIZED"
PARTS = {
    PFIA_REQUIREMENTS: {STATUTORY: "REQUIRED_CONTENT", ADVISORY: "COMMONLY_RESTATED"},
    AUTHORIZED_INVESTMENTS: {STATUTORY: "INSTRUMENT_TERMS", ADVISORY: "CONDITIONS_RESTATED"},
    GTOT: {STATUTORY: "CRITERIA", ADVISORY: "CRITERIA"},
    POLICY_GOVERNANCE: {STATUTORY: "SUMMARY", ADVISORY: "SUMMARY"},
}

# Section disposition, first matching rule wins (ADR 0010).
REVIEW_IN_PROGRESS = "REVIEW_IN_PROGRESS"
REVISIONS_RECOMMENDED = "REVISIONS_RECOMMENDED"
ADDITIONS_RECOMMENDED = "ADDITIONS_RECOMMENDED"
ADDRESSES_PROVISIONS_REVIEWED = "ADDRESSES_PROVISIONS_REVIEWED"
NOT_ASSESSED = "NOT_ASSESSED"


def route(authority: str, schedule: str) -> str:
    if authority == "GTOT" or schedule == "C":
        return GTOT
    if schedule == "B":
        return AUTHORIZED_INVESTMENTS
    return PFIA_REQUIREMENTS


@dataclass
class ElementResult:
    element_id: str
    assertion: str
    satisfied: bool
    basis: str
    band: str = STATUTORY
    spans: list[Span] = field(default_factory=list)


@dataclass
class Finding:
    control_id: str
    schedule: str
    title: str
    citation: str
    severity: str
    verdict: str
    applicable: bool
    status: str = NOT_APPLICABLE
    section: str = PFIA_REQUIREMENTS
    authority: str = "STATUTE"
    normative_force: str = ""
    reasons: list[str] = field(default_factory=list)
    unanswered_facts: list[str] = field(default_factory=list)
    elements: list[ElementResult] = field(default_factory=list)
    anti_pattern_hits: list[Span] = field(default_factory=list)
    substitutes: list[str] = field(default_factory=list)
    conditions_flagged: list[Mapping[str, Any]] = field(default_factory=list)
    band: str = STATUTORY
    # Status of elements in the other band, where a control's elements span both.
    advisory_status: str | None = None
    review_action: str = ""
    advisory_only: bool = False
    deficiency_language: str = ""
    remediation_language: str = ""
    extractor: str = ""
    discarded_claims: list[Mapping[str, Any]] = field(default_factory=list)
    retrieval_trace: list[str] = field(default_factory=list)

    @property
    def in_scope(self) -> bool:
        """Applicable and activated: the finding says something about this policy."""
        return self.applicable and self.verdict not in (NOT_APPLICABLE, APPLICABILITY_UNRESOLVED)

    @property
    def unresolved(self) -> bool:
        return self.verdict == APPLICABILITY_UNRESOLVED

    @property
    def part(self) -> str:
        return PARTS[self.section][self.band]


@dataclass
class ReviewResult:
    findings: list[Finding]
    context: Mapping[str, Any]

    def in_scope(self, band: str | None = None, section: str | None = None) -> list[Finding]:
        return [
            f for f in self.findings
            if f.in_scope and (band is None or f.band == band)
            and (section is None or f.section == section)
        ]

    def unresolved(self, section: str | None = None) -> list[Finding]:
        """Controls whose applicability could not be determined from the profile or policy."""
        return [f for f in self.findings if f.unresolved and (section is None or f.section == section)]

    def by_status(self, section: str | None = None) -> dict[str, dict[str, int]]:
        """Counts of item statuses per section part. A count describes; it is not a score."""
        out: dict[str, dict[str, int]] = {}
        for f in self.findings:
            if section is not None and f.section != section:
                continue
            if not (f.in_scope or f.unresolved):
                continue
            status = REVIEW_REQUIRED if f.unresolved else f.status
            bucket = out.setdefault(f.part, {})
            bucket[status] = bucket.get(status, 0) + 1
            if f.advisory_status:
                other = PARTS[f.section][ADVISORY]
                b2 = out.setdefault(other, {})
                b2[f.advisory_status] = b2.get(f.advisory_status, 0) + 1
        return out

    def disposition(self, section: str) -> dict[str, Any]:
        """Section status by fixed rules, first match wins. Never derived from a count."""
        scoped = self.in_scope(section=section)
        unresolved = self.unresolved(section)
        statutory = [f for f in scoped if f.band == STATUTORY]
        conflicts = [f.control_id for f in statutory if f.status == CONFLICTS]
        additions = [f.control_id for f in statutory if f.status in (NOT_ADDRESSED, PARTIALLY_ADDRESSED)]
        if section == POLICY_GOVERNANCE:
            # A summary never sets a status: it lists what the policy addresses.
            return {"status": SUMMARIZED if (scoped or unresolved) else NOT_ASSESSED,
                    "conflicts": [], "additions": [],
                    "unresolved": sorted(f.control_id for f in unresolved),
                    "counts": self.by_status(section)}
        if not scoped and not unresolved:
            status = NOT_ASSESSED
        elif unresolved:
            status = REVIEW_IN_PROGRESS
        elif conflicts:
            status = REVISIONS_RECOMMENDED
        elif additions:
            status = ADDITIONS_RECOMMENDED
        else:
            status = ADDRESSES_PROVISIONS_REVIEWED
        return {
            "status": status,
            "conflicts": sorted(conflicts),
            "additions": sorted(additions),
            "unresolved": sorted(f.control_id for f in unresolved),
            "counts": self.by_status(section),
        }

    def sections(self) -> dict[str, dict[str, Any]]:
        present = {f.section for f in self.findings}
        return {s: self.disposition(s) for s in SECTIONS
                if s in (AUTHORIZED_INVESTMENTS, PFIA_REQUIREMENTS) or s in present}


def summarize(finding: Finding) -> Finding:
    """Reduce a CONTEXT finding to one line: addressed or not expressly addressed.

    No element-level status, no conflict, no advisory split. The full evaluation is kept in
    `elements` for the trail; only what is reported changes.
    """
    finding.section = POLICY_GOVERNANCE
    finding.advisory_status = None
    if not finding.in_scope:
        return finding
    addressed = any(e.satisfied for e in finding.elements) or finding.status == ALIGNED_BY_REFERENCE
    finding.status = ALIGNED if addressed else NOT_ADDRESSED
    finding.verdict = CONFORMING if addressed else ABSENT
    finding.review_action = "SUMMARY_ONLY"
    finding.reasons = [
        "context provision (ADR 0011): summarized as addressed or not expressly addressed; "
        "not reviewed element by element"
    ]
    return finding


def _statutory_limit(fact_test: Any) -> float | None:
    """The numeric literal a conditional fact test compares against."""
    if isinstance(fact_test, Mapping):
        for op, args in fact_test.items():
            if op in ("<=", "<", ">=", ">") and isinstance(args, list) and len(args) == 2:
                for side in args:
                    if isinstance(side, (int, float)) and not isinstance(side, bool):
                        return float(side)
            for value in ([args] if not isinstance(args, list) else args):
                found = _statutory_limit(value)
                if found is not None:
                    return found
    elif isinstance(fact_test, list):
        for item in fact_test:
            found = _statutory_limit(item)
            if found is not None:
                return found
    return None


def _stated_figure(element: Any, facts: Mapping[str, Any]) -> float | None:
    referenced: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "var" and isinstance(value, str) and value.startswith("facts."):
                    referenced.append(value.split(".", 1)[1])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(element.fact_test)
    for name in referenced:
        value = (facts or {}).get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _fact_context(element: Any, facts: Mapping[str, Any]) -> dict[str, Any]:
    """Build the fact context, marking referenced-but-unstated figures UNKNOWN.

    A missing key would otherwise resolve to None and fail the comparison closed, which
    reads as a policy that stated a non-conforming figure rather than one that stated
    none at all.
    """
    from .profile import _walk_vars

    paths: set[str] = set()
    _walk_vars({"facts": element.fact_test}, paths)  # collects nothing; see below
    referenced: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key == "var" and isinstance(value, str) and value.startswith("facts."):
                    referenced.add(value.split(".", 1)[1])
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(element.fact_test)
    resolved = dict(facts or {})
    for name in referenced:
        if resolved.get(name) is None:
            resolved[name] = UNKNOWN
    return {"facts": resolved}


def _predicate_tri(rs: RegisterSet, ref: str, ctx: Mapping[str, Any]) -> Any:
    """Three-valued predicate evaluation. UNKNOWN means the profile did not say."""
    return jsonlogic.test_tri(rs.predicates[ref]["logic"], ctx)


def _predicate_true(rs: RegisterSet, ref: str, ctx: Mapping[str, Any]) -> bool:
    value = _predicate_tri(rs, ref, ctx)
    return False if value is UNKNOWN else value


def _unknown_facts(rs: RegisterSet, ref: str, ctx: Mapping[str, Any]) -> list[str]:
    """Name the unanswered entity facts a predicate depends on, for the finding."""
    from .profile import _walk_vars  # local import keeps the module import graph acyclic

    paths: set[str] = set()
    _walk_vars(rs.predicates[ref]["logic"], paths)
    unanswered: list[str] = []
    for path in sorted(paths):
        node: Any = ctx
        for part in path.split("."):
            node = node.get(part) if isinstance(node, Mapping) else None
        if node is UNKNOWN:
            unanswered.append(path)
    return unanswered


def _class_match(control: Control, entity_classes: list[str]) -> tuple[bool, str | None]:
    include = control.applicability.get("include_classes", ["*"])
    exclude = control.applicability.get("exclude_classes", [])
    hit = set(entity_classes) & set(exclude)
    if hit:
        return False, f"entity class excluded: {sorted(hit)}"
    if "*" in include:
        return True, None
    if set(entity_classes) & set(include):
        return True, None
    return False, f"entity classes {entity_classes} outside include set {include}"


def _activated(control: Control, ctx: Mapping[str, Any], rs: RegisterSet) -> tuple[Any, str]:
    """Return True, False or UNKNOWN for activation, with the reason."""
    act = control.activation
    if act.get("always"):
        return True, "always active"
    if "predicate_ref" in act:
        ref = act["predicate_ref"]
        hit = _predicate_tri(rs, ref, ctx)
        if hit is UNKNOWN:
            return UNKNOWN, f"activation predicate {ref} depends on unanswered entity facts"
        return hit, f"activation predicate {ref} evaluated {str(hit).lower()}"
    if "instrument_authorized" in act:
        code = act["instrument_authorized"]
        policy = ctx.get("policy", {})
        authorized = policy.get("authorized_instruments")
        if authorized is None:
            return UNKNOWN, (
                f"instrument {code}: no authorized-investment set was supplied or detected"
            )
        if code in authorized:
            # Positively identified in the document. Definite whether or not the wider set
            # is closed.
            return True, f"instrument {code} is in the policy's authorized set"
        if policy.get("authorization_unresolved"):
            # The set is a lower bound rather than a list, so absence from it proves
            # nothing. Returning False here would read, in every downstream artifact,
            # exactly like a policy that declines to authorize this instrument.
            return UNKNOWN, (
                f"instrument {code}: the policy's authorized-investment list is not closed "
                f"({policy.get('authorization_state', 'unresolved')}), so its absence from "
                "the detected set is not a determination"
            )
        return False, f"instrument {code} is not in the policy's authorized set"
    if "logic" in act:
        value = jsonlogic.test_tri(act["logic"], ctx)
        if value is UNKNOWN:
            return UNKNOWN, "inline activation logic depends on unanswered facts"
        return value, "inline activation logic"
    return True, "no activation clause; defaulting to active"


def evaluate_control(
    control: Control,
    rs: RegisterSet,
    ctx: Mapping[str, Any],
    extractor: Extractor,
    document: str,
    register_gate_ok: Any,
    authority: str = "STATUTE",
) -> Finding:
    bands = {e.id: BAND_BY_EXPECTATION[control.element_expectation(e)] for e in control.elements}
    finding = Finding(
        control_id=control.control_id,
        schedule=control.schedule,
        title=control.title,
        citation=control.cite_label,
        severity=control.severity,
        normative_force=control.normative_force,
        verdict=NOT_APPLICABLE,
        applicable=False,
        authority=authority,
        section=route(authority, control.schedule),
        # A control sits in the statutory band if any of its elements does; its advisory
        # elements are then reported alongside as advisory_status.
        band=STATUTORY if STATUTORY in bands.values() else ADVISORY,
        advisory_only=control.advisory_only,
        deficiency_language=control.deficiency_language,
        remediation_language=control.remediation_language,
    )

    if register_gate_ok is UNKNOWN:
        # Whether the subchapter reaches this entity at all is unanswered. Reporting that
        # as "excluded" would be a determination nobody made, and it would silently zero
        # out the entire review.
        finding.verdict = APPLICABILITY_UNRESOLVED
        finding.status = REVIEW_REQUIRED
        finding.reasons.append(
            "whether Subchapter A applies to this entity is unresolved: the Sec. 2256.004 "
            "exclusion questions have not been answered"
        )
        return finding
    if not register_gate_ok:
        finding.reasons.append("register gate not satisfied (Sec. 2256.004 exclusion)")
        return finding

    for ref in control.applicability.get("predicate_refs", []):
        value = _predicate_tri(rs, ref, ctx)
        if value is UNKNOWN:
            finding.verdict = APPLICABILITY_UNRESOLVED
            finding.status = REVIEW_REQUIRED
            unanswered = _unknown_facts(rs, ref, ctx)
            finding.unanswered_facts = unanswered
            finding.reasons.append(
                f"applicability predicate {ref} cannot be resolved: "
                + ", ".join(unanswered or ["an unanswered entity fact"])
            )
            return finding
        if not value:
            finding.reasons.append(f"applicability predicate {ref} false")
            return finding

    ok, why = _class_match(control, ctx.get("entity", {}).get("classes", []))
    if not ok:
        finding.reasons.append(why or "entity class mismatch")
        return finding

    for ex in control.exemptions:
        if ex.effect == "NARROWS_OPERATIVE_CLAUSE":
            continue
        if ex.effect == "SATISFIED_BY_REFERENCE":
            value = (
                _predicate_tri(rs, ex.predicate_ref, ctx)
                if ex.predicate_ref
                else jsonlogic.test_tri(ex.logic, ctx)
            )
            if value is UNKNOWN:
                finding.applicable = False
                finding.verdict = APPLICABILITY_UNRESOLVED
                finding.status = REVIEW_REQUIRED
                finding.reasons.append(
                    f"whether {ex.cite} incorporation applies is unresolved"
                )
                return finding
            if value:
                # The requirement is met by reference rather than by recitation. That is a
                # positive finding, not an exemption: the conditions are in the policy, and
                # a reader is directed to them. Recording it as NOT_APPLICABLE would drop
                # the control silently and lose the reason it passed.
                finding.applicable = True
                finding.verdict = CONFORMING
                finding.status = ALIGNED_BY_REFERENCE
                finding.reasons.append(ex.note or f"satisfied by reference under {ex.cite}")
                for element in control.elements:
                    finding.elements.append(
                        ElementResult(
                            element_id=element.id,
                            assertion=element.assertion,
                            satisfied=True,
                            basis="incorporated by reference",
                            band=bands[element.id],
                        )
                    )
                return finding
            continue
        if not (ex.predicate_ref or ex.logic):
            continue
        value = (
            _predicate_tri(rs, ex.predicate_ref, ctx)
            if ex.predicate_ref
            else jsonlogic.test_tri(ex.logic, ctx)
        )
        if value is UNKNOWN:
            # Whether the exemption attaches is unanswerable, so whether the control is
            # in scope is unanswerable too. Guessing either way is a finding the reviewer
            # never made.
            finding.verdict = APPLICABILITY_UNRESOLVED
            finding.status = REVIEW_REQUIRED
            unanswered = _unknown_facts(rs, ex.predicate_ref, ctx) if ex.predicate_ref else []
            finding.unanswered_facts = unanswered
            finding.reasons.append(
                f"exemption {ex.cite} cannot be resolved: "
                + ", ".join(unanswered or ["an unanswered entity fact"])
            )
            return finding
        if ex.negate:
            value = not value
        if value:
            finding.reasons.append(f"exemption {ex.cite} applies ({ex.effect})")
            if ex.substitute_control_id:
                finding.substitutes.append(ex.substitute_control_id)
            return finding

    active, activation_reason = _activated(control, ctx, rs)
    if active is UNKNOWN:
        finding.applicable = False
        finding.verdict = APPLICABILITY_UNRESOLVED
        finding.status = REVIEW_REQUIRED
        finding.reasons.append(activation_reason)
        return finding
    finding.applicable = True
    if not active:
        if control.inverted:
            # Prohibition controls invert: silence is compliance.
            finding.verdict = CONFORMING
            finding.status = ALIGNED
            finding.reasons.append("prohibited instrument not authorized by the policy")
        else:
            finding.applicable = False
            finding.reasons.append(f"not activated ({activation_reason})")
        return finding

    extraction: ControlExtraction = extractor.extract(control, document)
    finding.extractor = extraction.extractor
    finding.retrieval_trace = extraction.retrieval_trace
    finding.discarded_claims = list(extraction.discarded_claims)
    finding.anti_pattern_hits = extraction.anti_pattern_hits

    contradicted_figures: list[str] = []
    contradicted_elements: list[str] = []
    from .adapter.payload import anchored

    for element in control.elements:
        satisfied = bool(extraction.elements_satisfied.get(element.id, False))
        basis = "extractor assertion"
        if element.negative:
            # Resolved here, from the document, rather than taken from the extraction.
            # A negative element is a literal search and must give the same answer whether
            # the payload came from a live run, a cassette or a cache. It honours the
            # control's anti_pattern_anchors, as the runner does (EA-2026-09-27).
            hits: list[tuple[int, int]] = []
            for phrase in element.contradicted_by:
                hits.extend(h for h in _find_literal(phrase, document)
                            if anchored(control, document, h[0], h[1]))
            satisfied = not hits
            basis = "absence of contradicting language" if satisfied else "contradicted"
            if not satisfied:
                contradicted_elements.append(element.id)
            finding.elements.append(
                ElementResult(
                    element_id=element.id, assertion=element.assertion,
                    satisfied=satisfied, basis=basis, band=bands[element.id],
                    spans=[Span(start, end, document[start:end]) for start, end in hits[:3]],
                )
            )
            continue
        if element.fact_test is not None:
            value = jsonlogic.test_tri(element.fact_test, _fact_context(element, extraction.facts))
            if value is UNKNOWN:
                # The policy states no figure for this term. A conditional element is
                # satisfied by that silence; a mandatory one still needs the figure.
                satisfied = element.conditional
                basis = "no stated figure" if element.conditional else "figure not stated"
            else:
                satisfied = bool(value)
                basis = "fact test"
                limit = _statutory_limit(element.fact_test)
                stated = _stated_figure(element, extraction.facts)
                if not satisfied and stated is not None:
                    contradicted_figures.append(
                        f"{element.id}: the policy states {stated:g} where the statute allows "
                        + (f"{limit:g}" if limit is not None else "less")
                    )
                if satisfied and limit is not None and stated is not None and stated < limit:
                    # Every tier below the statutory cap is a narrowing, and Sec. 2256.024
                    # makes a policy stricter than the chapter conforming.
                    basis = "fact test (stricter than statute)"
                    finding.reasons.append(
                        f"the policy's stated limit ({stated:g}) is stricter than the "
                        f"statutory limit ({limit:g}); Sec. 2256.024 makes a more "
                        "restrictive policy conforming"
                    )
        finding.elements.append(
            ElementResult(
                element_id=element.id,
                assertion=element.assertion,
                satisfied=satisfied,
                basis=basis,
                band=bands[element.id],
                spans=extraction.spans.get(element.id, []),
            )
        )

    if control.inverted:
        # Activated prohibition: the policy authorized what the statute forbids.
        finding.verdict = DEFICIENT
        finding.status = CONFLICTS
        finding.reasons.append("policy authorizes an instrument prohibited by statute")
        finding.conditions_flagged = [c for c in control.conditions]
        return finding

    anti_effect = control.test.get("anti_pattern_effect", "DEFICIENT")
    anti = bool(extraction.anti_pattern_hits) and anti_effect == DEFICIENT
    if contradicted_figures:
        finding.reasons.extend(contradicted_figures)
    if anti:
        finding.reasons.append(
            f"{len(extraction.anti_pattern_hits)} anti-pattern hit(s): "
            + control.test.get("anti_pattern_rationale", "qualifying language defeats the mandate")
        )
    if contradicted_elements:
        finding.reasons.append(
            "contradicting language located for " + ", ".join(contradicted_elements)
        )
    # A conflict is stated language the statute does not permit: a figure beyond the limit,
    # an anti-pattern, or language that defeats a negative element. It is a different
    # finding from silence, with a different remedy (fix the clause, not draft one).
    conflict = bool(contradicted_figures or anti or contradicted_elements)

    primary = [e for e in finding.elements if e.band == finding.band]
    secondary = [e for e in finding.elements if e.band != finding.band]
    met = sum(1 for e in primary if e.satisfied)

    if conflict:
        finding.verdict = DEFICIENT
        finding.status = CONFLICTS
        if contradicted_figures:
            finding.reasons.append(
                "the policy states a term that exceeds the statutory limit; this is a stated "
                "conflict rather than an omission"
            )
        if met == 0:
            finding.reasons.append(
                "subject is addressed but in non-conforming terms; no element satisfied"
            )
    elif met == len(primary):
        finding.verdict = CONFORMING
        finding.status = ALIGNED
    elif met == 0:
        finding.verdict = ABSENT
        finding.status = NOT_ADDRESSED
        # Two different absences, and a reviewer needs to know which.
        if not extraction.windows_found:
            finding.reasons.append(
                "no candidate passage located anywhere in the document after a full sweep "
                "for every search directive"
            )
        else:
            finding.reasons.append(
                "candidate passages were located but none supported any required element; "
                "check the extraction before treating this as a policy gap"
            )
    else:
        finding.verdict = DEFICIENT
        finding.status = PARTIALLY_ADDRESSED
        finding.reasons.append("one or more required elements unsatisfied")

    if secondary:
        s_met = sum(1 for e in secondary if e.satisfied)
        finding.advisory_status = (
            ALIGNED if s_met == len(secondary) else NOT_ADDRESSED if s_met == 0 else PARTIALLY_ADDRESSED
        )

    if finding.verdict != CONFORMING and finding.band == ADVISORY:
        finding.reasons.append(
            "advisory band (policy_text_expectation=RECOMMENDED_NOT_REQUIRED): the statute "
            "does not require the policy to state this; it never sets a section's status"
        )

    finding.conditions_flagged = [c for c in control.conditions if c.get("severity") in ("HIGH", "CRITICAL")]
    finding.review_action = _review_action(finding, control, extraction)
    return finding


# What a reviewer has to do with this finding. The register is an ingestion engine that
# flags candidates for human review, so the deficiency list is a work queue rather than an
# accusation list - and the cheapest way to make it one is to say, per item, which kind of
# check it needs. These are different jobs taking different amounts of time, and sorting
# them is worth more than any refinement of the ordering.
REVIEW_ACTIONS = {
    "VERIFY_EXTRACTION": "A quotation was discarded or the extractor is not review-grade. "
                         "Check the passage before treating this as a policy gap.",
    "CONFIRM_ABSENCE": "Nothing matching this subject was found anywhere in the document. "
                       "Confirm the policy is genuinely silent rather than phrased in words "
                       "the register does not search for.",
    "READ_THE_PASSAGE": "Language known to defeat this requirement was located. Read the "
                        "passage: this is either a real defect or a phrase used differently.",
    "INTERPRETIVE": "The controlling text is contested or the control rests on a reading. "
                    "A judgment call, not a lookup.",
    "REVIEW_FINDING": "Elements unsatisfied on located evidence. Ordinary review.",
    "NONE": "",
}


def _review_action(finding: Finding, control: Control, extraction: ControlExtraction) -> str:
    if finding.verdict == CONFORMING:
        return "NONE"
    if extraction.discarded_claims or extraction.extractor.startswith(("heuristic", "keyword", "unlabelled")):
        return "VERIFY_EXTRACTION"
    if control.raw.get("interpretive"):
        return "INTERPRETIVE"
    if finding.anti_pattern_hits:
        return "READ_THE_PASSAGE"
    if finding.verdict == ABSENT and not extraction.windows_found:
        return "CONFIRM_ABSENCE"
    return "REVIEW_FINDING"


def review(
    rs: RegisterSet,
    entity_profile: Mapping[str, Any],
    policy_facts: Mapping[str, Any],
    document: str,
    extractor: Extractor,
    context_depth: str = SUMMARY,
) -> ReviewResult:
    """Evaluate every control in the register set against one policy document."""
    profile = dict(entity_profile)
    profile["classes"] = rs.expand_classes(list(profile.get("classes", [])))
    ctx: dict[str, Any] = {"entity": profile, "policy": dict(policy_facts)}

    findings: list[Finding] = []
    for register in rs.registers:
        gate_values = [
            _predicate_tri(rs, ref, ctx)
            for ref in register.register_gate.get("predicate_refs", [])
        ]
        if any(v is False for v in gate_values):
            gate_ok: Any = False
        elif any(v is UNKNOWN for v in gate_values):
            gate_ok = UNKNOWN
        else:
            gate_ok = True
        for control in register.controls:
            finding = evaluate_control(control, rs, ctx, extractor, document, gate_ok, register.authority)
            if control.relevance == "CONTEXT" and context_depth == SUMMARY:
                finding = summarize(finding)
            findings.append(finding)
    return ReviewResult(findings=findings, context=ctx)
