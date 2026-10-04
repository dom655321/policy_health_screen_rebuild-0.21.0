"""Register loading, reference resolution and structural validation.

Option B (normalized register) means predicates, entity classes and controls live in
separate documents joined by ID. Every join is resolved and checked here so that a
dangling reference fails at load time rather than silently evaluating to false during
a client review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import RegisterLoadError
from .model import Control, Element, Exemption, Register

VALID_EFFECTS = {
    "NOT_APPLICABLE", "SUBSTITUTE_CONTROL", "NARROWS_OPERATIVE_CLAUSE",
    # Met by reference rather than by recitation. A positive verdict, not an exemption.
    "SATISFIED_BY_REFERENCE",
}
VALID_FORCE = {
    "MANDATORY_CONTENT",
    "MANDATORY_CONDUCT",
    "PROHIBITION",
    "PERMISSIVE_ENABLING_WITH_CONDITIONS",
    "DEFINITIONAL",
}
VALID_EXPECTATION = {"REQUIRED", "RECOMMENDED", "RECOMMENDED_NOT_REQUIRED"}


@dataclass
class RegisterSet:
    """Everything needed to evaluate: shared taxonomy plus one or more registers."""

    entity_classes: dict[str, dict[str, Any]]
    predicates: dict[str, dict[str, Any]]
    registers: tuple[Register, ...]

    @property
    def controls(self) -> tuple[Control, ...]:
        return tuple(c for r in self.registers for c in r.controls)

    def control(self, control_id: str) -> Control | None:
        return next((c for c in self.controls if c.control_id == control_id), None)

    def expand_classes(self, classes: list[str]) -> list[str]:
        """Expand class membership transitively through `parent` links."""
        seen: list[str] = []
        stack = list(classes)
        while stack:
            cid = stack.pop()
            if cid in seen:
                continue
            if cid not in self.entity_classes:
                raise RegisterLoadError(f"unknown entity class in profile: {cid}")
            seen.append(cid)
            parent = self.entity_classes[cid].get("parent")
            if parent:
                stack.append(parent)
        return sorted(seen)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegisterLoadError(f"missing register file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegisterLoadError(f"invalid JSON in {path}: {exc}") from exc


def _build_element(raw: Mapping[str, Any], control_id: str) -> Element:
    for key in ("id", "assertion"):
        if key not in raw:
            raise RegisterLoadError(f"{control_id}: element missing {key!r}")
    if raw.get("conditional") and not raw.get("fact_test"):
        raise RegisterLoadError(
            f"{control_id}: element {raw['id']} is conditional but has no fact_test; a "
            "conditional element is a test on a figure the policy may or may not state"
        )
    if raw.get("negative") and not raw.get("contradicted_by"):
        raise RegisterLoadError(
            f"{control_id}: element {raw['id']} is negative but names no contradicting "
            "language; a negative element is tested by searching for what would defeat it"
        )
    return Element(
        id=raw["id"],
        assertion=raw["assertion"],
        test_type=raw.get("test_type"),
        fact_test=raw.get("fact_test"),
        negative=bool(raw.get("negative", False)),
        contradicted_by=tuple(raw.get("contradicted_by", ())),
        conditional=bool(raw.get("conditional", False)),
        policy_text_expectation=raw.get("policy_text_expectation"),
    )


def _relevance(control_id: str, raw: Mapping[str, Any]) -> str:
    value = raw.get("relevance", "CORE")
    if value not in ("CORE", "CONTEXT"):
        raise RegisterLoadError(f"{control_id}: relevance must be CORE or CONTEXT")
    return value


def _build_exemption(raw: Mapping[str, Any], control_id: str) -> Exemption:
    effect = raw.get("effect")
    if effect not in VALID_EFFECTS:
        raise RegisterLoadError(f"{control_id}: invalid exemption effect {effect!r}")
    if effect == "SUBSTITUTE_CONTROL" and not raw.get("substitute_control_id"):
        raise RegisterLoadError(f"{control_id}: SUBSTITUTE_CONTROL exemption needs substitute_control_id")
    return Exemption(
        cite=raw.get("cite", ""),
        effect=effect,
        predicate_ref=raw.get("predicate_ref"),
        logic=raw.get("logic"),
        negate=bool(raw.get("negate", False)),
        scope=raw.get("scope"),
        substitute_control_id=raw.get("substitute_control_id"),
        applies_to=tuple(raw.get("applies_to", ())),
        note=raw.get("note"),
    )


def _build_control(raw: Mapping[str, Any], register: Mapping[str, Any]) -> Control:
    control_id = raw.get("control_id")
    if not control_id:
        raise RegisterLoadError(f"{register['$id']}: control without control_id")
    force = raw.get("normative_force")
    if force not in VALID_FORCE:
        raise RegisterLoadError(f"{control_id}: invalid normative_force {force!r}")
    if "policy_text_expectation" not in raw:
        # Previously defaulted to REQUIRED, which put an unlabelled control in the statutory
        # band without anyone deciding so (IS-2256.009-b-001, element audit EA-2026-09-27).
        raise RegisterLoadError(f"{control_id}: policy_text_expectation is required")
    expectation = raw["policy_text_expectation"]
    if expectation not in VALID_EXPECTATION:
        raise RegisterLoadError(f"{control_id}: invalid policy_text_expectation {expectation!r}")

    elements = tuple(_build_element(e, control_id) for e in raw.get("required_elements", []))
    if not elements:
        raise RegisterLoadError(f"{control_id}: at least one required element is mandatory")
    for e in elements:
        if e.policy_text_expectation is not None and e.policy_text_expectation not in VALID_EXPECTATION:
            raise RegisterLoadError(f"{control_id}: element {e.id} has invalid policy_text_expectation")
    if len({e.id for e in elements}) != len(elements):
        raise RegisterLoadError(f"{control_id}: duplicate element ids")

    return Control(
        control_id=control_id,
        schedule=register.get("schedule", "?"),
        register_id=register["$id"],
        title=raw.get("title", ""),
        citation=raw.get("citation", {}),
        source_text=raw.get("source_text", ""),
        normative_force=force,
        severity=raw.get("severity", "MEDIUM"),
        operative_clause=raw.get("operative_clause", ""),
        elements=elements,
        exemptions=tuple(_build_exemption(x, control_id) for x in raw.get("exemptions", [])),
        conditions=tuple(raw.get("conditions", [])),
        applicability=raw.get("applicability", {}),
        activation=raw.get("activation", {"always": True}),
        test=raw.get("test", {}),
        evidence_locus=tuple(raw.get("evidence_locus", ())),
        policy_text_expectation=expectation,
        relevance=_relevance(control_id, raw),
        instrument_code=raw.get("instrument_code"),
        inverted=bool(raw.get("inverted", False)),
        deficiency_language=raw.get("deficiency_language", ""),
        remediation_language=raw.get("remediation_language", ""),
        cross_references=tuple(raw.get("cross_references", ())),
        raw=raw,
    )


def load(root: Path, register_dirs: list[str] | None = None) -> RegisterSet:
    """Load the shared taxonomy and the named register directories under `root`."""
    root = Path(root)
    classes_doc = _read_json(root / "entity_classes.json")
    predicates_doc = _read_json(root / "predicates.json")

    entity_classes = {c["id"]: c for c in classes_doc["entity_classes"]}
    predicates = {p["id"]: p for p in predicates_doc["predicates"]}

    for cid, cls in entity_classes.items():
        parent = cls.get("parent")
        if parent and parent not in entity_classes:
            raise RegisterLoadError(f"entity class {cid} references unknown parent {parent}")

    explicit = bool(register_dirs)
    dirs = register_dirs or [p.name for p in sorted(root.iterdir()) if p.is_dir()]
    registers: list[Register] = []
    for name in dirs:
        doc = _read_json(root / name / "register.json")
        if doc.get("status") in ("proposed", "paused") and not explicit:
            # A proposed register is under review: it lives in the repository, validates
            # against the schema and is covered by tests, but it does not score a policy
            # until someone adopts it. Naming it explicitly loads it anyway, which is how
            # a reviewer sees what it would do.
            continue
        controls = tuple(_build_control(c, doc) for c in doc.get("controls", []))
        registers.append(
            Register(
                id=doc["$id"],
                schedule=doc.get("schedule", "?"),
                title=doc.get("title", ""),
                version=doc.get("version", ""),
                authority=doc.get("authority", "STATUTE"),
                law_in_force_as_of=doc.get("law_in_force_as_of", ""),
                canonical_source=doc.get("canonical_source", ""),
                register_gate=doc.get("register_gate", {}),
                controls=controls,
                instruments=tuple(doc.get("instruments", ())),
                raw=doc,
            )
        )

    rs = RegisterSet(entity_classes=entity_classes, predicates=predicates, registers=tuple(registers))
    _validate_references(rs)
    return rs


def _validate_references(rs: RegisterSet) -> None:
    known_controls = {c.control_id for c in rs.controls}
    known_instruments = {
        i["code"] for r in rs.registers for i in r.instruments
    }
    for register in rs.registers:
        for ref in register.register_gate.get("predicate_refs", []):
            if ref not in rs.predicates:
                raise RegisterLoadError(f"{register.id}: register_gate references unknown predicate {ref}")
    loaded_prefixes = {c.control_id.split("-")[0] for c in rs.controls}
    for control in rs.controls:
        # Cross references were loaded and never checked. A reference into a register that
        # is loaded must resolve; a reference into one that is not (a proposed GTOT
        # register, say) is left alone until that register loads.
        refs = list(control.cross_references) + [
            c["linked_control"] for c in control.conditions if isinstance(c, Mapping) and c.get("linked_control")
        ]
        for target in refs:
            if target.split("-")[0] in loaded_prefixes and target not in known_controls:
                raise RegisterLoadError(f"{control.control_id}: cross reference {target} does not resolve")
        for ref in control.applicability.get("predicate_refs", []):
            if ref not in rs.predicates:
                raise RegisterLoadError(f"{control.control_id}: unknown predicate ref {ref}")
        for cls in list(control.applicability.get("include_classes", [])) + list(
            control.applicability.get("exclude_classes", [])
        ):
            if cls != "*" and cls not in rs.entity_classes:
                raise RegisterLoadError(f"{control.control_id}: unknown entity class {cls}")
        ref = control.activation.get("predicate_ref")
        if ref and ref not in rs.predicates:
            raise RegisterLoadError(f"{control.control_id}: activation references unknown predicate {ref}")
        code = control.activation.get("instrument_authorized")
        if code and known_instruments and code not in known_instruments:
            raise RegisterLoadError(f"{control.control_id}: unknown instrument code {code}")
        for ex in control.exemptions:
            if ex.predicate_ref and ex.predicate_ref not in rs.predicates:
                raise RegisterLoadError(f"{control.control_id}: exemption references unknown predicate {ex.predicate_ref}")
            if ex.substitute_control_id and ex.substitute_control_id not in known_controls:
                raise RegisterLoadError(
                    f"{control.control_id}: substitute control {ex.substitute_control_id} is not in the loaded set"
                )
