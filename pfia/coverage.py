"""Statutory coverage: what the register does not test.

A review that scores 49 controls and says nothing about the rest of the chapter invites
the reader to assume the rest was examined and found clean. It was not examined at all.
Nothing in a verdict, a score or a deficiency list distinguishes those two states, so the
distinction has to be carried separately, computed from the section inventory rather than
asserted in prose.

Coverage is entity-aware. Sec. 2256.0204 is uncovered, but telling a water authority it has
an uncovered gap in the independent school district corporate bond provision is noise that
buries the gaps that do apply to it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import PFIAError
from .loader import RegisterSet

COVERAGE_FILE = "coverage.json"
TESTABLE = "in_scope"


class CoverageError(PFIAError):
    """Raised when the register cites a section the inventory does not contain."""


@dataclass
class SectionCoverage:
    section: str
    title: str
    review_status: str
    entity_classes: tuple[str, ...]
    control_ids: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def covered(self) -> bool:
        return bool(self.control_ids)

    @property
    def testable(self) -> bool:
        return self.review_status == TESTABLE


@dataclass
class CoverageReport:
    sections: list[SectionCoverage]
    entity_classes: tuple[str, ...] = ()

    def _applicable(self) -> list[SectionCoverage]:
        if not self.entity_classes:
            return [s for s in self.sections if s.testable]
        classes = set(self.entity_classes)
        return [
            s for s in self.sections
            if s.testable and (not s.entity_classes or classes & set(s.entity_classes))
        ]

    @property
    def testable_sections(self) -> list[SectionCoverage]:
        return self._applicable()

    @property
    def covered_sections(self) -> list[SectionCoverage]:
        return [s for s in self._applicable() if s.covered]

    @property
    def uncovered_sections(self) -> list[SectionCoverage]:
        return [s for s in self._applicable() if not s.covered]

    @property
    def ratio(self) -> float:
        applicable = self._applicable()
        if not applicable:
            return 1.0
        return round(len(self.covered_sections) / len(applicable), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_classes": list(self.entity_classes),
            "sections_testable": len(self.testable_sections),
            "sections_covered": len(self.covered_sections),
            "section_coverage_ratio": self.ratio,
            "uncovered": [
                {"section": s.section, "title": s.title, "note": s.note}
                for s in self.uncovered_sections
            ],
            "covered": [
                {"section": s.section, "controls": len(s.control_ids)}
                for s in self.covered_sections
            ],
            "statement": (
                f"{len(self.covered_sections)} of {len(self.testable_sections)} testable "
                "sections of Subchapter A carry at least one control for this entity class. "
                "Sections with no control were not evaluated; their absence from the findings "
                "is not a determination of compliance."
            ),
        }


def load_inventory(registers_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(registers_dir) / COVERAGE_FILE).read_text(encoding="utf-8"))


def build(rs: RegisterSet, registers_dir: str | Path,
          entity_classes: Iterable[str] = ()) -> CoverageReport:
    inventory = load_inventory(registers_dir)
    by_section: dict[str, SectionCoverage] = {}
    for entry in inventory["sections"]:
        by_section[entry["section"]] = SectionCoverage(
            section=entry["section"],
            title=entry["title"],
            review_status=entry["review_status"],
            entity_classes=tuple(entry.get("entity_classes", ())),
            note=entry.get("note", ""),
        )

    unknown: set[str] = set()
    for control in rs.controls:
        section = control.citation.get("section", "")
        if section not in by_section:
            unknown.add(section)
            continue
        by_section[section].control_ids.append(control.control_id)

    if unknown:
        raise CoverageError(
            "controls cite sections that are not in the coverage inventory: "
            + ", ".join(sorted(unknown))
            + ". Either the citation is wrong or the inventory is stale; both are defects."
        )

    return CoverageReport(sections=list(by_section.values()), entity_classes=tuple(entity_classes))
