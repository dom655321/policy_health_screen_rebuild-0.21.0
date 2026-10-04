"""Statutory coverage: what the register does not test, stated rather than implied."""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.coverage import CoverageError, build, load_inventory

BASE = Path(__file__).resolve().parents[1]
REGISTERS = BASE / "data" / "registers"


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.inventory = load_inventory(REGISTERS)

    def test_sections_are_unique(self):
        sections = [s["section"] for s in self.inventory["sections"]]
        self.assertEqual(len(sections), len(set(sections)))

    def test_every_cited_section_exists_in_the_inventory(self):
        # build() raises when a control cites a section the inventory lacks, which catches
        # both a mistyped citation and a stale inventory.
        build(self.rs, REGISTERS)

    def test_unknown_section_is_rejected(self):
        class Fake:
            controls = ()
        broken = loader.load(REGISTERS)
        control = broken.controls[0]
        object.__setattr__(control, "citation", {"section": "2256.999"})
        with self.assertRaises(CoverageError):
            build(broken, REGISTERS)

    def test_skipped_section_is_absent(self):
        sections = {s["section"] for s in self.inventory["sections"]}
        self.assertNotIn("2256.018", sections)
        self.assertIn("2256.0115", sections)
        self.assertIn("2256.0208", sections)


class TestCoverageReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)

    def test_coverage_is_entity_aware(self):
        water = build(self.rs, REGISTERS, ["LOCAL_GOV", "DISTRICT_ART3_52B_ART16_59", "WATER_DISTRICT_36_49"])
        everything = build(self.rs, REGISTERS)
        self.assertLess(len(water.testable_sections), len(everything.testable_sections))
        water_sections = {s.section for s in water.testable_sections}
        # Sections scoped to other entity classes are out of scope entirely, not gaps.
        self.assertNotIn("2256.0207", water_sections)
        self.assertNotIn("2256.020", water_sections)
        self.assertIn("2256.0208", water_sections)

    def test_subchapter_is_fully_covered(self):
        """Every testable section of Subchapter A now carries at least one control."""
        for classes in ([], ["LOCAL_GOV"], ["STATE_AGENCY"], ["ISD_1371_ISSUER"], ["IHE"]):
            with self.subTest(classes=classes):
                report = build(self.rs, REGISTERS, classes)
                self.assertEqual(report.uncovered_sections, [], report.to_dict()["uncovered"])
                self.assertEqual(report.ratio, 1.0)

    def test_a_gap_would_still_be_reported(self):
        """Full coverage must not be an artefact of the mechanism failing quietly."""
        rs = loader.load(REGISTERS)
        survivors = tuple(
            r.__class__(**{**r.__dict__, "controls": tuple(
                c for c in r.controls if c.citation.get("section") != "2256.026")})
            for r in rs.registers
        )
        rs.registers = survivors
        report = build(rs, REGISTERS, ["LOCAL_GOV"])
        self.assertIn("2256.026", {s.section for s in report.uncovered_sections})
        self.assertLess(report.ratio, 1.0)

    def test_definitional_sections_are_not_gaps(self):
        report = build(self.rs, REGISTERS)
        uncovered = {s.section for s in report.uncovered_sections}
        for section in ("2256.001", "2256.002", "2256.004", "2256.024", "2256.022"):
            self.assertNotIn(section, uncovered)

    def test_ratio_is_bounded_and_matches_the_lists(self):
        report = build(self.rs, REGISTERS, ["LOCAL_GOV"])
        self.assertGreater(report.ratio, 0.0)
        self.assertLessEqual(report.ratio, 1.0)
        self.assertEqual(
            len(report.covered_sections) + len(report.uncovered_sections),
            len(report.testable_sections),
        )

    def test_report_states_that_gaps_are_not_findings(self):
        payload = build(self.rs, REGISTERS, ["LOCAL_GOV"]).to_dict()
        self.assertIn("not a determination of compliance", payload["statement"])
        self.assertEqual(payload["uncovered"], [])
        self.assertEqual(payload["sections_covered"], payload["sections_testable"])


if __name__ == "__main__":
    unittest.main()


class TestLedgerIntegration(unittest.TestCase):
    """The three unknowns must reach the ledger, not just the console."""

    @classmethod
    def setUpClass(cls):
        from pfia.evaluate import review
        from pfia.extraction import KeywordExtractor
        from pfia.instruments import detect
        from pfia.ledger import build_ledger
        from pfia.profile import load as load_profile

        rs = loader.load(REGISTERS)
        profiles = BASE / "data" / "profiles"
        document = (BASE / "tests" / "fixtures" / "policy_deficient.txt").read_text()
        entity, report = load_profile(rs, profiles / "city.json", profiles)
        resolution = detect(rs, document, REGISTERS)
        result = review(rs, entity, resolution.to_facts(), document, KeywordExtractor())
        cls.ledger = build_ledger(
            rs, result, document, "policy_deficient.txt", "keyword-baseline",
            coverage=build(rs, REGISTERS, entity["classes"]),
            profile_report=report, instruments=resolution,
        )

    def test_ledger_carries_coverage(self):
        coverage = self.ledger["coverage"]
        self.assertGreater(coverage["sections_testable"], 0)
        self.assertEqual(coverage["sections_covered"], coverage["sections_testable"])
        self.assertIn("not a determination of compliance", coverage["statement"])

    def test_ledger_carries_the_instrument_resolution(self):
        instruments = self.ledger["instruments"]
        self.assertEqual(instruments["state"], "blanket_incorporation")
        self.assertTrue(instruments["unresolved"])
        self.assertTrue(instruments["reasons"])

    def test_ledger_carries_the_profile_state(self):
        self.assertTrue(self.ledger["profile"]["complete"])
        self.assertEqual(self.ledger["profile"]["unanswered"], [])

    def test_ledger_lists_unresolved_controls_separately_from_scores(self):
        unresolved = self.ledger["unresolved"]
        self.assertTrue(unresolved)
        self.assertEqual(len(unresolved), self.ledger["unresolved_controls"])
        scored_ids = {
            f["control_id"] for f in self.ledger["findings"] if f["in_scope"]
        }
        self.assertFalse(scored_ids & {u["control_id"] for u in unresolved})

    def test_ledger_is_json_serializable_with_unanswered_facts(self):
        import json as _json

        from pfia.evaluate import review
        from pfia.extraction import NullExtractor
        from pfia.ledger import build_ledger
        from pfia.profile import build_context, load_field_specs

        rs = loader.load(REGISTERS)
        profiles = BASE / "data" / "profiles"
        raw = _json.loads((profiles / "city.json").read_text())
        raw["has_pooled_fund_groups"] = None
        entity, report = build_context(rs, raw, load_field_specs(profiles))
        result = review(rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        ledger = build_ledger(rs, result, "", "x", "null", profile_report=report)
        text = _json.dumps(ledger)
        self.assertIn('"UNKNOWN"', text)
