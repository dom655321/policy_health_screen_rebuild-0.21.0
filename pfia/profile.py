"""Entity profile: the questions a reviewer must answer, and what happens if they do not.

The applicable set is a function of the entity profile. Twelve of the fifty controls in
this register gate on it, and several gate on it decisively - Sec. 2256.005(f) switches off
entirely for an entity whose investment function is assigned by law, and every training
control switches off for a Water Code ch. 36 or 49 district. A hand-typed profile with a
plausible default in the wrong slot produces a confident, wrong review.

Two things follow, and this module implements both.

**The required field set is derived, never maintained by hand.** It is read out of the
predicates the loaded registers actually reference, so a new predicate automatically
demands its question. `data/profiles/fields.json` supplies the wording, and the two are
checked against each other in both directions: a derived field with no question fails, and
a question with no consumer fails.

**An unanswered question is not an answer.** A missing field becomes UNKNOWN rather than
false, and the three-valued predicate evaluator carries it through to a verdict of
APPLICABILITY_UNRESOLVED. The alternative - two-valued logic over a partly blank profile -
silently drops controls out of the applicable set, and nothing downstream can tell that
apart from a control the legislature never pointed at this entity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import PFIAError
from .jsonlogic import UNKNOWN
from .loader import RegisterSet

FIELDS_FILE = "fields.json"


class ProfileError(PFIAError):
    """Raised when a profile cannot be reconciled with the register."""


@dataclass(frozen=True)
class FieldSpec:
    path: str
    type: str
    question: str
    cite: str = ""
    help: str = ""
    nullable: bool = True

    @property
    def key(self) -> str:
        """The path without the `entity.` prefix."""
        return self.path.split(".", 1)[1]


@dataclass
class ProfileReport:
    """What is answered, what is not, and what that costs."""

    answered: list[str] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    # Answers accepted after a harmless normalization ("yes" -> true, "$250,000,000" ->
    # 250000000, "municipality" -> MUNICIPALITY), reported so nothing changes silently.
    normalized: list[str] = field(default_factory=list)
    unknown_extra: list[str] = field(default_factory=list)
    blocked_controls: dict[str, list[str]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.unanswered

    def summary(self) -> str:
        blocked = sum(len(v) for v in self.blocked_controls.values())
        return (
            f"{len(self.answered)} answered, {len(self.unanswered)} unanswered; "
            f"{len(self.blocked_controls)} control(s) unresolved"
            + (f" across {blocked} dependency link(s)" if blocked else "")
        )


def _walk_vars(node: Any, out: set[str]) -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "var" and isinstance(value, str) and value.startswith("entity."):
                out.add(value)
            else:
                _walk_vars(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_vars(item, out)


def required_paths(rs: RegisterSet) -> set[str]:
    """Every `entity.*` fact path the loaded registers can read."""
    paths: set[str] = set()
    for predicate in rs.predicates.values():
        _walk_vars(predicate["logic"], paths)
    for control in rs.controls:
        _walk_vars(control.activation, paths)
        for exemption in control.exemptions:
            if exemption.logic:
                _walk_vars(exemption.logic, paths)
    return paths


def load_field_specs(profiles_dir: str | Path) -> dict[str, FieldSpec]:
    path = Path(profiles_dir) / FIELDS_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"missing profile field metadata: {path}") from exc
    specs: dict[str, FieldSpec] = {}
    for entry in document["fields"]:
        spec = FieldSpec(
            path=entry["path"],
            type=entry["type"],
            question=entry["question"],
            cite=entry.get("cite", ""),
            help=entry.get("help", ""),
            nullable=entry.get("nullable", True),
        )
        specs[spec.path] = spec
    return specs


def reconcile(rs: RegisterSet, specs: Mapping[str, FieldSpec]) -> tuple[set[str], set[str]]:
    """Return (fields with no question, questions with no consumer)."""
    derived = required_paths(rs)
    documented = set(specs)
    return derived - documented, documented - derived


def _get(profile: Mapping[str, Any], key: str) -> Any:
    node: Any = profile
    for part in key.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return None
        node = node[part]
    return node


def _set(target: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = target
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def dependants(rs: RegisterSet, paths: Iterable[str]) -> dict[str, list[str]]:
    """Map each unanswered fact path to the controls that read it."""
    wanted = set(paths)
    out: dict[str, list[str]] = {}
    predicate_paths: dict[str, set[str]] = {}
    for name, predicate in rs.predicates.items():
        found: set[str] = set()
        _walk_vars(predicate["logic"], found)
        predicate_paths[name] = found

    for control in rs.controls:
        reads: set[str] = set()
        for ref in control.applicability.get("predicate_refs", []):
            reads |= predicate_paths.get(ref, set())
        ref = control.activation.get("predicate_ref")
        if ref:
            reads |= predicate_paths.get(ref, set())
        _walk_vars(control.activation, reads)
        for exemption in control.exemptions:
            if exemption.predicate_ref:
                reads |= predicate_paths.get(exemption.predicate_ref, set())
            if exemption.logic:
                _walk_vars(exemption.logic, reads)
        for path in reads & wanted:
            out.setdefault(path, []).append(control.control_id)
    return {path: sorted(controls) for path, controls in out.items()}


_TRUE = {"true", "yes", "y", "t"}
_FALSE = {"false", "no", "n", "f"}


def _normalize_classes(rs: RegisterSet, raw: Any, report: "ProfileReport") -> list[str]:
    """Validate entity.classes, accepting a bare string and lower-case IDs.

    A string used to be passed to list(), which split "yes" into "y", "e", "s" and failed
    with "unknown entity class: y". Now each problem is named with the IDs to choose from.
    """
    import difflib

    valid = sorted(rs.entity_classes)
    listing = "\n".join(f"  {cid:<32} {rs.entity_classes[cid].get('label', '')}" for cid in valid)
    if isinstance(raw, str):
        report.normalized.append(f"entity.classes: {raw!r} -> [{raw!r}]")
        raw = [raw]
    if not isinstance(raw, list) or not all(isinstance(c, str) for c in raw):
        raise ProfileError(
            "entity.classes must be a list of class IDs, for example [\"MUNICIPALITY\"].\n\n"
            "Available classes:\n" + listing)
    out, bad = [], []
    for cid in raw:
        key = cid.strip()
        if key in rs.entity_classes:
            out.append(key)
        elif key.upper() in rs.entity_classes:
            report.normalized.append(f"entity.classes: {cid!r} -> {key.upper()!r}")
            out.append(key.upper())
        else:
            bad.append(cid)
    if bad:
        hints = []
        for cid in bad:
            if cid.strip().lower() in _TRUE | _FALSE:
                hints.append(f"  {cid!r} looks like a yes/no answer; classes takes class IDs")
            else:
                close = difflib.get_close_matches(cid.strip().upper(), valid, n=1)
                hints.append(f"  {cid!r}: unknown" + (f" (did you mean {close[0]}?)" if close else ""))
        raise ProfileError(
            "entity.classes contains values that are not entity class IDs:\n" + "\n".join(hints)
            + "\n\nUse the IDs below, for example [\"MUNICIPALITY\"] for a city. Parent classes "
            "are added automatically.\n\nAvailable classes:\n" + listing)
    return out


def _normalize_answer(spec: "FieldSpec", value: Any, report: "ProfileReport") -> Any:
    """Check an answer against its declared type; accept unambiguous everyday forms."""
    path = spec.path
    if spec.type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            coerced = value.strip().lower() in _TRUE
            report.normalized.append(f"{path}: {value!r} -> {str(coerced).lower()}")
            return coerced
        # A string such as "no" is truthy; passing it through would make a control apply
        # when the answer was the opposite. Refuse rather than guess.
        raise ProfileError(f"{path} must be true or false (or null if unknown); got {value!r}")
    if spec.type in ("number", "integer"):
        number = value
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace("$", "").replace("_", "")
            try:
                number = float(cleaned)
            except ValueError:
                raise ProfileError(f"{path} must be a number (or null if unknown); got {value!r}") from None
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ProfileError(f"{path} must be a number (or null if unknown); got {value!r}")
        if spec.type == "integer":
            if float(number) != int(number):
                raise ProfileError(f"{path} must be a whole number; got {value!r}")
            number = int(number)
        if number != value:
            report.normalized.append(f"{path}: {value!r} -> {number!r}")
        return number
    return value


def build_context(
    rs: RegisterSet, profile: Mapping[str, Any], specs: Mapping[str, FieldSpec]
) -> tuple[dict[str, Any], ProfileReport]:
    """Expand classes, substitute UNKNOWN for unanswered facts, and report the gaps."""
    # Keys beginning with an underscore are questionnaire scaffolding, not entity facts.
    entity = json.loads(json.dumps({k: v for k, v in profile.items() if not k.startswith("_")}))
    classes = entity.get("classes")
    if not classes:
        available = "\n".join(
            f"  {cid:<32} {spec.get('label', '')}"
            for cid, spec in sorted(rs.entity_classes.items())
        )
        raise ProfileError(
            "entity.classes is empty. Without it no control's applicability can be resolved, "
            "so this is the one question that cannot be left unanswered.\n\n"
            "Choose every class that describes the entity; parent classes are added "
            "automatically, so a tollway authority needs only TOLLWAY_AUTHORITY and not "
            "LOCAL_GOV as well.\n\nAvailable classes:\n" + available
        )
    report = ProfileReport()
    entity["classes"] = rs.expand_classes(_normalize_classes(rs, classes, report))

    for path, spec in sorted(specs.items()):
        if spec.path == "entity.classes":
            report.answered.append(path)
            continue
        value = _get(entity, spec.key)
        if value is None:
            if not spec.nullable:
                raise ProfileError(f"{path} is required and was left unanswered")
            _set(entity, spec.key, UNKNOWN)
            report.unanswered.append(path)
        else:
            _set(entity, spec.key, _normalize_answer(spec, value, report))
            report.answered.append(path)

    report.blocked_controls = dependants(rs, report.unanswered)
    return entity, report


def load(rs: RegisterSet, path: str | Path, profiles_dir: str | Path) -> tuple[dict[str, Any], ProfileReport]:
    """Load a profile file and prepare it for evaluation."""
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    specs = load_field_specs(profiles_dir)
    missing, orphaned = reconcile(rs, specs)
    if missing:
        raise ProfileError(
            "the register reads entity facts that no profile question covers: "
            + ", ".join(sorted(missing))
        )
    return build_context(rs, profile, specs)


def impact(
    rs: RegisterSet,
    profile: Mapping[str, Any],
    specs: Mapping[str, FieldSpec],
    instruments: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """For each unanswered field, which controls it leaves unresolved.

    Most questions in the questionnaire do not apply to most entities: they gate controls
    that reach a different class entirely. Telling a reviewer which of their blanks
    actually matter is the difference between a form and an interrogation.

    Every instrument code is assumed authorized unless a set is given. That is deliberately
    the worst case: a field that gates only an instrument the policy does not authorize
    would otherwise be reported as harmless, and the reviewer would leave it blank before
    discovering the policy does authorize it.

    One caveat worth stating. Each field is isolated by answering the other blanks with
    false or zero, so a field can be reported harmless because a different blank
    short-circuits the predicate it shares - Sec. 2256.0206 eligibility is a conjunction of
    a debt threshold and a rating test, and a false rating makes the threshold moot. Answer
    the questions in order and re-run; the report tightens as the profile fills in.
    """
    from .evaluate import APPLICABILITY_UNRESOLVED, review  # local import breaks the cycle
    from .extraction import NullExtractor

    if instruments is None:
        instruments = sorted(
            {i["code"] for register in rs.registers for i in register.instruments}
        )
    facts = {"authorized_instruments": list(instruments)}

    _entity, report = build_context(rs, profile, specs)
    out: dict[str, list[str]] = {}
    for path in report.unanswered:
        probe = json.loads(json.dumps({k: v for k, v in profile.items()
                                       if not k.startswith("_")}))
        for spec in specs.values():
            if spec.path in ("entity.classes", path):
                continue
            if _get(probe, spec.key) is None:
                # Placeholder so this field's effect is isolated from the other blanks.
                _set(probe, spec.key, 0 if spec.type in ("number", "integer") else False)
        entity, _ = build_context(rs, probe, specs)
        result = review(rs, entity, facts, "", NullExtractor())
        out[path] = sorted(
            f.control_id for f in result.findings if f.verdict == APPLICABILITY_UNRESOLVED
        )
    return out


def questionnaire(rs: RegisterSet, specs: Mapping[str, FieldSpec], entity_name: str = "") -> dict[str, Any]:
    """Produce a blank profile with every question unanswered and annotated."""
    blank: dict[str, Any] = {"entity_name": entity_name, "classes": []}
    questions: dict[str, Any] = {}
    dependency = dependants(rs, [s.path for s in specs.values()])
    for spec in sorted(specs.values(), key=lambda s: s.path):
        if spec.path == "entity.classes":
            continue
        _set(blank, spec.key, None)
        questions[spec.path] = {
            "question": spec.question,
            "type": spec.type,
            "cite": spec.cite,
            "help": spec.help,
            "controls_that_depend_on_it": dependency.get(spec.path, []),
        }
    blank["_questions"] = questions
    blank["_entity_classes"] = {
        cid: {
            "label": spec.get("label", ""),
            "cite": spec.get("cite", ""),
            "parent": spec.get("parent"),
            "note": spec.get("note", ""),
        }
        for cid, spec in sorted(rs.entity_classes.items())
    }
    blank["_how_to_answer"] = {
        "classes": "A list of IDs from _entity_classes, for example [\"MUNICIPALITY\"] for a city. "
                   "Parent classes are added automatically.",
        "boolean": "true or false, without quotes.",
        "number": "A plain number, for example 250000000.",
        "unknown": "null. The dependent controls are reported as unresolved, never guessed.",
    }
    blank["_note"] = (
        "Leave a field null if you do not know the answer. An unanswered field is carried "
        "as UNKNOWN and the controls that depend on it are reported as "
        "APPLICABILITY_UNRESOLVED rather than being silently dropped. Delete the _questions "
        "and _note keys once the profile is complete, or leave them; both are ignored."
    )
    return blank
