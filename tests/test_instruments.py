"""Reading the authorized-investment set out of the policy itself."""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import APPLICABILITY_UNRESOLVED, review
from pfia.extraction import NullExtractor
from pfia.instruments import detect, load_lexicon

BASE = Path(__file__).resolve().parents[1]
REGISTERS = BASE / "data" / "registers"
FIX = BASE / "tests" / "fixtures"
PROFILES = BASE / "data" / "profiles"


def _doc(name):
    return (FIX / name).read_text(encoding="utf-8")


class TestDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)

    def _detect(self, name):
        return detect(self.rs, _doc(name), REGISTERS)

    def test_enumerated_policy_resolves(self):
        resolution = self._detect("policy_conforming.txt")
        self.assertEqual(resolution.state, "enumerated")
        self.assertFalse(resolution.unresolved)
        self.assertEqual(
            resolution.authorized,
            ["COMMERCIAL_PAPER", "DEPOSITORY_CD", "INVESTMENT_POOL", "REPO", "US_OBLIGATIONS"],
        )

    def test_prohibited_derivatives_are_read_as_excluded_not_authorized(self):
        """The regression that matters most: 'are not authorized' must not read as
        'authorized'. Getting this wrong fabricates a CRITICAL finding."""
        resolution = self._detect("policy_conforming.txt")
        self.assertIn("CMO_IO_PO_INVERSE", resolution.excluded)
        self.assertNotIn("CMO_IO_PO_INVERSE", resolution.authorized)

    def test_exclusion_survives_into_the_prohibition_control(self):
        entity = json.loads((PROFILES / "water_authority.json").read_text())
        facts = self._detect("policy_conforming.txt").to_facts()
        result = review(self.rs, entity, facts, _doc("policy_conforming.txt"), NullExtractor())
        finding = next(f for f in result.findings if f.control_id == "IS-2256.009-b-001")
        self.assertEqual(finding.verdict, "CONFORMING")

    def test_blanket_incorporation_leaves_the_set_open(self):
        resolution = self._detect("policy_deficient.txt")
        self.assertEqual(resolution.state, "blanket_incorporation")
        self.assertTrue(resolution.unresolved)
        # Types named alongside the blanket clause are still authorized; the set is a
        # lower bound rather than a list.
        self.assertIn("DEPOSITORY_CD", resolution.authorized)
        self.assertTrue(resolution.to_facts()["authorization_unresolved"])

    def test_open_set_makes_undetected_instruments_unresolved_not_absent(self):
        entity = json.loads((PROFILES / "city.json").read_text())
        facts = self._detect("policy_deficient.txt").to_facts()
        result = review(self.rs, entity, facts, _doc("policy_deficient.txt"), NullExtractor())
        by_id = {f.control_id: f for f in result.findings}
        # Detected: scored normally.
        self.assertNotEqual(by_id["IS-2256.010-a-001"].verdict, APPLICABILITY_UNRESOLVED)
        # Not detected, but the set is not closed: undetermined, not inapplicable.
        self.assertEqual(by_id["IS-2256.015-001"].verdict, APPLICABILITY_UNRESOLVED)

    def test_missing_section_is_unresolved_not_empty(self):
        resolution = detect(self.rs, "This document says nothing about investments.", REGISTERS)
        self.assertEqual(resolution.state, "section_not_located")
        self.assertTrue(resolution.unresolved)
        self.assertEqual(resolution.authorized, [])

    def test_detection_reproduces_the_hand_written_fact_files(self):
        """Parity check: detection must be able to replace the hand-supplied facts."""
        pairs = [
            ("policy_conforming.txt", "facts_water_authority.json"),
            ("policy_isd.txt", "facts_isd.json"),
        ]
        for policy, facts_file in pairs:
            with self.subTest(policy=policy):
                detected = set(self._detect(policy).authorized)
                supplied = set(json.loads((FIX / facts_file).read_text())["authorized_instruments"])
                self.assertEqual(detected, supplied)

    def test_mentions_carry_verifiable_offsets(self):
        resolution = self._detect("policy_conforming.txt")
        document = _doc("policy_conforming.txt")
        for mention in resolution.mentions:
            self.assertEqual(
                document[mention.start:mention.end].lower().split(),
                mention.term.lower().split(),
            )

    def test_blanket_phrasing_is_read_from_the_control_not_restated(self):
        lexicon = load_lexicon(REGISTERS)
        control = self.rs.control("TX-PFIA-2256.005-b-4-A-001")
        self.assertTrue(control.test["anti_patterns"])
        for pattern in control.test["anti_patterns"]:
            self.assertNotIn(pattern, json.dumps(lexicon))


if __name__ == "__main__":
    unittest.main()


class TestEnumeratedListInheritance(unittest.TestCase):
    """The dominant Texas drafting pattern: one authorizing stem, then a bare list.

    "only the following investment types ... are authorized:" followed by (a) through (k)
    puts the authorization in the stem and leaves every instrument a bare noun phrase.
    Deciding polarity sentence by sentence reads the whole list as indeterminate and
    authorizes nothing, which is a silent under-report of every instrument control.
    """

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.resolution = detect(cls.rs, _doc("policy_enumerated_list.txt"), REGISTERS)

    def test_every_listed_instrument_is_detected(self):
        expected = {
            "US_OBLIGATIONS", "MUNI_OBLIGATIONS", "DEPOSITORY_CD", "REPO", "REVERSE_REPO",
            "BANKERS_ACCEPTANCE", "COMMERCIAL_PAPER", "MMMF", "MUTUAL_FUND",
            "INVESTMENT_POOL", "GIC", "INTEREST_BEARING_DEPOSIT",
        }
        self.assertEqual(set(self.resolution.authorized), expected)
        self.assertEqual(self.resolution.state, "enumerated")
        self.assertFalse(self.resolution.unresolved)

    def test_inheritance_is_recorded_on_the_mention(self):
        inherited = [m for m in self.resolution.mentions if m.inherited]
        self.assertTrue(inherited)
        for mention in inherited:
            self.assertEqual(mention.polarity, "authorizing")

    def test_scoped_exclusion_restricts_rather_than_removes(self):
        """"not authorized for bond proceeds, reserves and debt service" confines the
        instrument to other money; it does not de-authorize it."""
        self.assertIn("MUTUAL_FUND", self.resolution.authorized)
        self.assertIn("MUTUAL_FUND", self.resolution.restricted)
        self.assertNotIn("MUTUAL_FUND", self.resolution.excluded)

    def test_a_prohibition_section_beyond_the_list_still_excludes(self):
        self.assertIn("CMO_IO_PO_INVERSE", self.resolution.excluded)
        self.assertNotIn("CMO_IO_PO_INVERSE", self.resolution.authorized)

    def test_a_heading_ends_the_stem_reach(self):
        """Proxy voting and prohibited-investment sections sit past the list and must not
        inherit from it."""
        for mention in self.resolution.mentions:
            if mention.code == "CMO_IO_PO_INVERSE":
                self.assertFalse(mention.inherited)

    def test_inline_list_does_not_extend_reach(self):
        """A colon followed by prose rather than enumerated items has no reach.

        Without this bound, one "the following are authorized:" swallows the rest of the
        document, and an instrument named only in a settlement clause inherits
        authorization. The ISD fixture names mutual funds only in its DVP carve-out.
        """
        resolution = detect(self.rs, _doc("policy_isd.txt"), REGISTERS)
        self.assertNotIn("MUTUAL_FUND", resolution.authorized)
        self.assertEqual(
            set(resolution.authorized),
            {"US_OBLIGATIONS", "DEPOSITORY_CD", "INVESTMENT_POOL", "ISD_CORPORATE_BOND"},
        )

    def test_wildcard_section_directive_matches_an_interposed_name(self):
        """Headings interpose the entity's own name more often than not."""
        resolution = detect(
            self.rs,
            "Authorized Example System Investments.\n\nOnly the following investment types "
            "are authorized:\n\n  (a) commercial paper rated A-1.\n",
            REGISTERS,
        )
        self.assertTrue(resolution.sections)
        self.assertIn("COMMERCIAL_PAPER", resolution.authorized)

    def test_contradiction_keeps_the_instrument_and_records_the_conflict(self):
        resolution = detect(
            self.rs,
            "Authorized investments:\n\n  (a) commercial paper rated A-1/P-1.\n\n"
            "PROHIBITED INVESTMENTS\n\nCommercial paper is not authorized.\n",
            REGISTERS,
        )
        self.assertIn("COMMERCIAL_PAPER", resolution.authorized)
        self.assertIn("COMMERCIAL_PAPER", resolution.contradictions)
        self.assertTrue(any("different passages" in r for r in resolution.reasons))


class TestListTailAndDiagnostics(unittest.TestCase):
    """The tail of a long list is where the uncommon instruments sit."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)

    def test_the_last_item_of_a_long_list_is_reached(self):
        """A stem's reach must be a scan region in its own right.

        The section-heading window is a fixed span and a real list outruns it. Item (k) of
        the tollway fixture sits past that window, and scanning only the heading window
        silently dropped savings deposits - one instrument, at the end, invisible.
        """
        resolution = detect(self.rs, _doc("policy_enumerated_list.txt"), REGISTERS)
        self.assertIn("INTEREST_BEARING_DEPOSIT", resolution.authorized)
        self.assertEqual(len(resolution.authorized), 12)

    def test_reflowed_list_is_read_the_same_as_an_indented_one(self):
        """PDF extraction often reflows an indented block into running prose, leaving the
        (a)/(b)/(c) markers mid-line rather than at the start of one."""
        indented = detect(self.rs, _doc("policy_enumerated_list.txt"), REGISTERS)
        reflowed = detect(self.rs, _doc("policy_reflowed_list.txt"), REGISTERS)
        self.assertEqual(set(indented.authorized), set(reflowed.authorized))

    def test_stems_are_reported_for_diagnosis(self):
        resolution = detect(self.rs, _doc("policy_enumerated_list.txt"), REGISTERS)
        report = resolution.report()
        self.assertTrue(report["stems"])
        productive = [s for s in report["stems"] if s["instruments_inherited"]]
        self.assertTrue(productive)
        for stem in report["stems"]:
            for key in ("start", "end", "chars", "enumerated_markers", "preview"):
                self.assertIn(key, stem)

    def test_absence_of_a_stem_is_stated_in_the_trace(self):
        resolution = detect(self.rs, "Nothing here resembles an investment policy.", REGISTERS)
        self.assertTrue(any("no enumerated list stem" in t for t in resolution.directive_trace))

    def test_a_single_parenthetical_does_not_make_a_stem(self):
        """Requiring two markers keeps an unrelated aside from turning any authorizing
        sentence into a list stem."""
        text = ("Maximum maturities for any authorized investment are established in the "
                "Strategy.\n\n(I) Authorized System Investments.\n\nNothing follows.\n")
        resolution = detect(self.rs, text, REGISTERS)
        self.assertFalse([s for s in resolution.stems if s["instruments_inherited"]])


class TestVersionStamping(unittest.TestCase):
    """An artifact must be traceable to the code that produced it.

    Three separate diagnoses in this project were slowed by not knowing which version of
    the detector produced a result. Stamping it removes the question.
    """

    def test_detection_report_carries_both_versions(self):
        from pfia import __version__

        rs = loader.load(REGISTERS)
        report = detect(rs, _doc("policy_conforming.txt"), REGISTERS).report()
        self.assertEqual(report["package_version"], __version__)
        self.assertTrue(report["lexicon_version"])

    def test_ledger_carries_the_package_version(self):
        from pfia import __version__, coverage as coverage_module, profile as profile_module
        from pfia.evaluate import review
        from pfia.extraction import NullExtractor
        from pfia.ledger import build_ledger

        rs = loader.load(REGISTERS)
        profiles = REGISTERS.parent / "profiles"
        entity, _report = profile_module.load(rs, profiles / "city.json", profiles)
        result = review(rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        ledger = build_ledger(rs, result, "", "x", "null",
                              coverage=coverage_module.build(rs, REGISTERS, entity["classes"]))
        self.assertEqual(ledger["package_version"], __version__)


class TestUnindentedExtraction(unittest.TestCase):
    """Text extracted from a PDF arrives with every line at column zero.

    The reach loop originally treated a leading space as the test for whether a line
    continued the current list item. On a real document that ended the reach at the first
    wrapped line: a twelve-item list yielded one item, and the eleven instruments in the
    rest of it were reported NOT APPLICABLE - indistinguishable, everywhere downstream,
    from a policy that never authorized them.
    """

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)

    def test_layout_does_not_change_the_result(self):
        variants = {
            name: detect(self.rs, _doc(name), REGISTERS)
            for name in ("policy_enumerated_list.txt", "policy_unindented_list.txt",
                         "policy_reflowed_list.txt")
        }
        sets = {name: set(r.authorized) for name, r in variants.items()}
        self.assertEqual(len(set(map(frozenset, sets.values()))), 1, sets)
        for name, resolution in variants.items():
            self.assertEqual(len(resolution.authorized), 12, name)

    def test_reach_spans_the_whole_list_without_indentation(self):
        resolution = detect(self.rs, _doc("policy_unindented_list.txt"), REGISTERS)
        productive = [s for s in resolution.stems if s["instruments_inherited"]]
        self.assertEqual(len(productive), 1)
        self.assertGreater(productive[0]["chars"], 2000)
        self.assertGreaterEqual(len(productive[0]["instruments_inherited"]), 11)

    def test_reach_still_ends_after_the_list(self):
        """The bound is distance from the last item, so prose past the list is excluded and
        the prohibited-investments section keeps its own polarity."""
        resolution = detect(self.rs, _doc("policy_unindented_list.txt"), REGISTERS)
        self.assertIn("CMO_IO_PO_INVERSE", resolution.excluded)
        for mention in resolution.mentions:
            if mention.code == "CMO_IO_PO_INVERSE":
                self.assertFalse(mention.inherited)

    def test_inline_list_still_gets_no_reach(self):
        resolution = detect(self.rs, _doc("policy_isd.txt"), REGISTERS)
        self.assertEqual(resolution.stems, [])
        self.assertNotIn("MUTUAL_FUND", resolution.authorized)


class TestConformityElementInvariants(unittest.TestCase):
    """A conformity control's negative element must name exactly the control's
    anti-patterns. Two copies of the same list drift, and the copy that drifted here left
    a removed numeric limit still defeating the element."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)

    def test_contradicted_by_matches_the_anti_pattern_library(self):
        for control in self.rs.controls:
            if control.schedule != "B" or control.inverted:
                continue
            if control.policy_text_expectation != "REQUIRED":
                continue
            anti = list(control.test.get("anti_patterns", []))
            for element in control.elements:
                if element.negative and anti:
                    self.assertEqual(list(element.contradicted_by), anti, control.control_id)

    def test_no_numeric_limit_survives_as_an_anti_pattern(self):
        """A literal figure cannot tell a stricter limit from a looser one, and a stricter
        limit conforms under Sec. 2256.024. Figures belong in conditional fact tests."""
        # Each of these carries a digit but is not a limit a policy could satisfy more
        # strictly: a rating grade, a wrong section number, a structural defect, or the
        # signature of a different section's authority copied into this one.
        allowed = {"102 percent of the loaned value excluding accrued income",
                   "CMO with a stated final maturity greater than 10 years",
                   "501(c)(3)", "15 percent of its monthly average fund balance",
                   "Section 2256.0206", "A-2", "P-2"}
        for control in self.rs.controls:
            if control.schedule != "B":
                continue
            for phrase in control.test.get("anti_patterns", []):
                if any(ch.isdigit() for ch in phrase):
                    self.assertIn(phrase, allowed, f"{control.control_id}: {phrase!r}")
