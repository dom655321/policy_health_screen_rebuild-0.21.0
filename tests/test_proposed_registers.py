"""A register under review must be visible without being scored."""

import json
import unittest
from pathlib import Path

from pfia import loader

BASE = Path(__file__).resolve().parents[1]
REGISTERS = BASE / "data" / "registers"
GTOT = REGISTERS / "gtot-criteria" / "register.json"


class TestProposedRegisterIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(GTOT.read_text(encoding="utf-8"))
        cls.rs = loader.load(REGISTERS)

    def test_the_default_load_excludes_it(self):
        self.assertNotIn("tx-pfia/gtot-criteria", {r.id for r in self.rs.registers})
        self.assertEqual({r.schedule for r in self.rs.registers}, {"A", "B"})

    def test_naming_it_explicitly_loads_it(self):
        rs = loader.load(REGISTERS, ["gtot-criteria"])
        self.assertEqual([r.id for r in rs.registers], ["tx-pfia/gtot-criteria"])

    def test_it_is_marked_proposed(self):
        # Paused (ADR 0011): kept in the repository, loads only when named explicitly.
        self.assertEqual(self.doc["status"], "paused")

    def test_criteria_are_not_held_under_the_controls_key(self):
        """Held under `criteria` so changing the status flag alone cannot score it."""
        self.assertEqual(self.doc["controls"], [])
        self.assertTrue(self.doc["criteria"])

    def test_every_criterion_is_flagged_as_a_placeholder(self):
        for criterion in self.doc["criteria"]:
            self.assertTrue(criterion.get("placeholder"), criterion["control_id"])

    def test_adoption_requires_removing_every_placeholder(self):
        """The guard that matters: a placeholder criterion must never be scored, so a
        register cannot be adopted while any criterion still carries the flag."""
        if self.doc["status"] != "adopted":
            self.skipTest("register is still proposed")
        for criterion in self.doc.get("controls", []):
            self.assertFalse(criterion.get("placeholder"), criterion["control_id"])
            self.assertNotIn("PLACEHOLDER", criterion.get("source_text", ""))
            self.assertNotEqual(criterion.get("criterion_ref"), "UNKNOWN")

    def test_certification_criteria_are_advisory_by_construction(self):
        """A certification checklist cannot create a statutory obligation."""
        for criterion in self.doc["criteria"]:
            self.assertEqual(criterion["policy_text_expectation"],
                             "RECOMMENDED_NOT_REQUIRED", criterion["control_id"])
            self.assertEqual(criterion["severity"], "ADVISORY", criterion["control_id"])

    def test_each_criterion_records_its_relationship_to_the_statute(self):
        """Either it cross-references a statutory control, or it says it has no counterpart.
        Without that, one gap gets reported twice and a statutory finding is diluted into a
        certification observation."""
        for criterion in self.doc["criteria"]:
            has_link = bool(criterion.get("cross_references"))
            says_none = any("no statutory counterpart" in c.get("text", "")
                            for c in criterion.get("conditions", []))
            self.assertTrue(has_link or says_none, criterion["control_id"])

    def test_the_source_is_marked_for_replacement(self):
        self.assertIn("REPLACE", self.doc["canonical_source"])
        self.assertTrue(self.doc["READ_THIS_FIRST"])


if __name__ == "__main__":
    unittest.main()
