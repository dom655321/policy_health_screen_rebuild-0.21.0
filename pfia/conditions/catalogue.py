"""Load and validate the Schedule B v2 condition catalogue.

Validation is structural and evidential. Structural: ids unique, modes and components
known, inherited instruments present. Evidential: every condition's `quote` must appear
verbatim (modulo whitespace and typographic quotes) in the committed statute snapshot, so
no condition can assert a requirement the reviewer cannot find in the law.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

MODES = {"CAP", "FLOOR", "RATING_FLOOR", "SUBSET", "REQUIRED", "PROHIBITED", "ANY_OF"}
COMPONENTS = {
    "ISSUER", "COUNTERPARTY", "FORM", "CREDIT_RATING", "CREDIT_SUPPORT", "INSURANCE",
    "MATURITY", "CONCENTRATION", "COLLATERAL", "CUSTODY", "FUNDS_RESTRICTION", "GOVERNANCE",
    "DISPOSITION", "PROCUREMENT", "PURPOSE", "REGULATORY", "SEGREGATION", "MANAGER_DUTY",
    "PROHIBITION", "DISCLOSURE", "VALUATION", "PORTFOLIO", "USE_OF_PROCEEDS", "STRUCTURE",
}
BINDS = {"ENTITY", "POOL", "FUND", "INVESTMENT_MANAGER", "COUNTERPARTY", "SECURITY"}
RATING_SCALES = {"LONG_TERM", "SHORT_TERM", "POOL", "CD"}


_SECTION_HEAD = re.compile(r"Sec\. (2256\.\d+)\. ")
_CITED_SECTION = re.compile(r"2256\.\d+")


def split_sections(statute: str) -> dict[str, str]:
    """Normalized statute text keyed by section number ("2256.009" -> its full text)."""
    heads = list(_SECTION_HEAD.finditer(statute))
    out: dict[str, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(statute)
        out.setdefault(m.group(1), statute[m.start():end])
    return out


class CatalogueError(ValueError):
    """The catalogue failed structural or evidential validation."""


def normalize(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Condition:
    id: str
    instrument: str
    cite: str
    component: str
    binds: str
    requirement: str
    test: Mapping[str, Any]
    quote: str
    activation: Mapping[str, Any] | None = None
    note: str | None = None
    interpretive: str | None = None

    @property
    def mode(self) -> str:
        return self.test["mode"]


@dataclass(frozen=True)
class Instrument:
    code: str
    label: str
    authority: tuple[str, ...]
    entity_classes: tuple[str, ...]
    conditions: tuple[Condition, ...]
    inherits: tuple[str, ...] = ()
    lexicon_change: str | None = None
    note: str | None = None
    # Conditions removed in team review: kept for the audit trail, never evaluated.
    retired: tuple[Condition, ...] = ()
    # {"status": "NOT_REVIEWED", "reason": ...} when no condition remains active.
    scope: Mapping[str, Any] | None = None

    @property
    def not_reviewed(self) -> bool:
        return bool(self.scope) and self.scope.get("status") == "NOT_REVIEWED"


@dataclass
class Catalogue:
    meta: Mapping[str, Any]
    instruments: dict[str, Instrument] = field(default_factory=dict)

    def conditions_for(self, code: str) -> list[Condition]:
        """Own conditions plus inherited ones, own conditions first, no duplicates."""
        inst = self.instruments[code]
        seen, out = set(), []
        for cond in inst.conditions:
            seen.add(cond.id)
            out.append(cond)
        for parent in inst.inherits:
            for cond in self.conditions_for(parent):
                if cond.id not in seen:
                    seen.add(cond.id)
                    out.append(cond)
        return out

    @property
    def conditions(self) -> list[Condition]:
        return [c for i in self.instruments.values() for c in i.conditions]


def _condition(raw: Mapping[str, Any], code: str) -> Condition:
    return Condition(
        id=raw["id"], instrument=code, cite=raw["cite"], component=raw["component"],
        binds=raw["binds"], requirement=raw["requirement"], test=raw["test"], quote=raw["quote"],
        activation=raw.get("activation"), note=raw.get("note"), interpretive=raw.get("interpretive"),
    )


def _validate_test(cid: str, test: Mapping[str, Any], errors: list[str]) -> None:
    mode = test.get("mode")
    if mode not in MODES:
        errors.append(f"{cid}: unknown test mode {mode!r}")
        return
    if "fact" not in test:
        errors.append(f"{cid}: test has no fact key")
    if mode in {"CAP", "FLOOR"}:
        if not isinstance(test.get("limit"), (int, float)) or not test.get("unit"):
            errors.append(f"{cid}: {mode} needs numeric limit and unit")
    elif mode == "RATING_FLOOR":
        if test.get("scale") not in RATING_SCALES or not test.get("floor"):
            errors.append(f"{cid}: RATING_FLOOR needs a known scale and a floor")
        if test.get("granularity", "NOTCH") not in {"NOTCH", "CATEGORY"}:
            errors.append(f"{cid}: granularity must be NOTCH or CATEGORY")
    elif mode == "SUBSET":
        allowed = test.get("allowed")
        if not allowed or any(a.startswith("OTHER") for a in allowed):
            errors.append(f"{cid}: SUBSET needs a non-empty allowed list without OTHER codes")
    elif mode == "ANY_OF":
        alts = test.get("alternatives") or []
        ids = [a.get("id") for a in alts]
        if len(alts) < 2 or len(set(ids)) != len(ids):
            errors.append(f"{cid}: ANY_OF needs two or more uniquely identified alternatives")


def load_catalogue(path: str | Path, snapshot: str | Path | None = None, *, verify_quotes: bool = True) -> Catalogue:
    """Load the catalogue. Raises CatalogueError listing every problem found."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    cat = Catalogue(meta={k: v for k, v in doc.items() if k != "instruments"})

    sections: dict[str, str] | None = None
    if verify_quotes:
        snap = Path(snapshot) if snapshot else path.parents[3] / doc["snapshot"]
        if not snap.exists():
            raise CatalogueError(f"statute snapshot not found: {snap}")
        sections = split_sections(normalize(snap.read_text(encoding="utf-8")))

    seen_ids: set[str] = set()
    for raw_inst in doc["instruments"]:
        code = raw_inst["code"]
        if code in cat.instruments:
            errors.append(f"duplicate instrument code {code}")
        conds = []
        for raw in raw_inst["conditions"]:
            cid = raw.get("id", "?")
            if cid in seen_ids:
                errors.append(f"duplicate condition id {cid}")
            seen_ids.add(cid)
            if raw.get("component") not in COMPONENTS:
                errors.append(f"{cid}: unknown component {raw.get('component')!r}")
            if raw.get("binds") not in BINDS:
                errors.append(f"{cid}: unknown binds {raw.get('binds')!r}")
            _validate_test(cid, raw.get("test", {}), errors)
            if sections is not None:
                # The quote must appear inside a section the condition cites, so a short
                # phrase cannot pass by matching somewhere else in the chapter.
                cited = sorted(set(_CITED_SECTION.findall(raw.get("cite", ""))))
                quote = normalize(raw.get("quote", ""))
                missing = [c for c in cited if c not in sections]
                if not cited or missing:
                    errors.append(f"{cid}: cite {raw.get('cite')!r} names no section in the snapshot")
                elif not any(quote in sections[c] for c in cited):
                    errors.append(f"{cid}: quote not found verbatim in cited section(s) {', '.join(cited)}")
            conds.append(_condition(raw, code))
        cat.instruments[code] = Instrument(
            code=code, label=raw_inst["label"], authority=tuple(raw_inst["authority"]),
            entity_classes=tuple(raw_inst["entity_classes"]), conditions=tuple(conds),
            inherits=tuple(raw_inst.get("inherits", ())), lexicon_change=raw_inst.get("lexicon_change"),
            note=raw_inst.get("note"),
            retired=tuple(_condition(r, code) for r in raw_inst.get("retired_conditions", [])),
            scope=raw_inst.get("scope"),
        )
        if not conds and not (raw_inst.get("scope") or {}).get("status") == "NOT_REVIEWED":
            errors.append(f"{code}: no active conditions; mark scope NOT_REVIEWED rather than leave it empty")
    for inst in cat.instruments.values():
        for parent in inst.inherits:
            if parent not in cat.instruments:
                errors.append(f"{inst.code}: inherits unknown instrument {parent}")
    if errors:
        raise CatalogueError("; ".join(errors))
    return cat
