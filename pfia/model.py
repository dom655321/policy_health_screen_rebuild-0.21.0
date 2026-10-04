"""Typed views over register data.

The register is authored as JSON and stays JSON. These dataclasses are read-only
projections used by the evaluator so that field access is checked in one place
rather than scattered `dict.get` calls across the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

Verdict = str  # CONFORMING | DEFICIENT | ABSENT | NOT_APPLICABLE

SEVERITY_ORDER = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "ADVISORY": 0}


@dataclass(frozen=True)
class Element:
    id: str
    assertion: str
    test_type: str | None = None
    fact_test: Mapping[str, Any] | None = None
    negative: bool = False
    contradicted_by: tuple[str, ...] = ()
    conditional: bool = False
    # Element-level band (ADR 0010). None means the control's policy_text_expectation.
    policy_text_expectation: str | None = None

    @property
    def tested_by_absence(self) -> bool:
        """Satisfied unless the policy says something that defeats it.

        Two shapes: a negative element, defeated by named language; and a conditional
        fact element, defeated only by a stated figure that conflicts with the statute.
        A policy that states no figure has stated nothing wrong.
        """
        return self.negative or self.conditional

    @property
    def vacuously_satisfied(self) -> bool:
        """Satisfied by the absence of contradicting language rather than by a quote.

        Some statutory elements are limits on what a policy may say, not requirements of
        what it must say. "Any stated carve-out is limited to investment pool funds and
        mutual funds" is met perfectly by a policy that states no carve-out at all, and
        there is no passage to quote in support. Demanding an affirmative span for these
        fails the best-drafted policies and is the single largest source of spurious
        PARTIAL verdicts.
        """
        return self.negative


@dataclass(frozen=True)
class Exemption:
    cite: str
    effect: str  # NOT_APPLICABLE | SUBSTITUTE_CONTROL | NARROWS_OPERATIVE_CLAUSE
    predicate_ref: str | None = None
    logic: Mapping[str, Any] | None = None
    negate: bool = False
    scope: str | None = None
    substitute_control_id: str | None = None
    applies_to: tuple[str, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class Control:
    control_id: str
    schedule: str
    register_id: str
    title: str
    citation: Mapping[str, Any]
    source_text: str
    normative_force: str
    severity: str
    operative_clause: str
    elements: tuple[Element, ...]
    exemptions: tuple[Exemption, ...]
    conditions: tuple[Mapping[str, Any], ...]
    applicability: Mapping[str, Any]
    activation: Mapping[str, Any]
    test: Mapping[str, Any]
    policy_text_expectation: str
    relevance: str = "CORE"
    evidence_locus: tuple[str, ...] = ()
    instrument_code: str | None = None
    inverted: bool = False
    deficiency_language: str = ""
    remediation_language: str = ""
    cross_references: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def cite_label(self) -> str:
        c = self.citation
        parts = [f"Sec. {c.get('section', '')}"]
        if c.get("subsection"):
            parts.append(f"({c['subsection']})")
        if c.get("subdivision"):
            parts.append(f"({c['subdivision']})")
        if c.get("paragraph"):
            parts.append(f"({c['paragraph']})")
        return "".join(parts)

    def element_expectation(self, element: "Element") -> str:
        return element.policy_text_expectation or self.policy_text_expectation

    @property
    def advisory_only(self) -> bool:
        """True when the statute does not require the policy itself to speak."""
        return self.policy_text_expectation == "RECOMMENDED_NOT_REQUIRED"


@dataclass(frozen=True)
class Register:
    id: str
    schedule: str
    title: str
    version: str
    authority: str
    law_in_force_as_of: str
    canonical_source: str
    register_gate: Mapping[str, Any]
    controls: tuple[Control, ...]
    instruments: tuple[Mapping[str, Any], ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)
