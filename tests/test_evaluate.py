import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import review
from pfia.extraction import KeywordExtractor, PrecomputedExtractor
from pfia.ledger import build_ledger

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "data" / "registers"
FIX = BASE / "tests" / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TestEvaluate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.water = _json(BASE / "data" / "profiles" / "water_authority.json")
        cls.city = _json(BASE / "data" / "profiles" / "city.json")
        cls.facts = _json(FIX / "facts_water_authority.json")

    def _finding(self, result, control_id):
        return next(f for f in result.findings if f.control_id == control_id)

    def test_anti_pattern_caps_score_and_marks_deficient(self):
        result = review(self.rs, self.city, self.facts, _read("policy_deficient.txt"), KeywordExtractor())
        dvp = self._finding(result, "TX-PFIA-2256.005-b-4-E-001")
        self.assertEqual(dvp.verdict, "DEFICIENT")
        self.assertEqual(dvp.status, "CONFLICTS")
        self.assertTrue(dvp.anti_pattern_hits)

    def test_absent_when_no_span_located(self):
        result = review(self.rs, self.city, self.facts, "This document says nothing relevant.", KeywordExtractor(),
                        context_depth="FULL")
        finding = self._finding(result, "TX-PFIA-2256.005-e-001")
        self.assertEqual(finding.verdict, "ABSENT")
        # KeywordExtractor does not report windows_found, so the finding falls to the
        # conservative reading: passages may have been located and simply not supported.
        self.assertIn("candidate passage", finding.reasons[0])

    def test_fact_test_overrides_extractor_assertion(self):
        """A stated figure decides the element; the extractor's own assertion does not."""
        payload = _json(FIX / "extraction_water_authority.json")
        result = review(self.rs, self.water, self.facts, _read("policy_conforming.txt"),
                        PrecomputedExtractor(payload, source="fixture"))
        conformity = self._finding(result, "IS-2256.013-001")
        fact_element = next(e for e in conformity.elements if e.element_id.startswith("f"))
        self.assertTrue(fact_element.basis.startswith("fact test"))
        self.assertTrue(fact_element.satisfied)  # the policy states 270, and 270 <= 365

        completeness = self._finding(result, "IS-2256.013-002")
        self.assertEqual(completeness.band, "ADVISORY")

    def test_unstated_figure_does_not_fail_a_conditional_element(self):
        """A policy that names commercial paper without stating a maturity has stated
        nothing that conflicts with Sec. 2256.013."""
        result = review(self.rs, self.water, self.facts,
                        "Authorized investments include commercial paper.", KeywordExtractor())
        conformity = self._finding(result, "IS-2256.013-001")
        for element in conformity.elements:
            if element.element_id.startswith("f"):
                self.assertTrue(element.satisfied)
                self.assertEqual(element.basis, "no stated figure")

    def test_composite_index_excludes_inapplicable_controls(self):
        result = review(self.rs, self.water, self.facts, _read("policy_conforming.txt"), KeywordExtractor())
        scoped = result.in_scope()
        self.assertTrue(all(f.applicable for f in scoped))
        self.assertLess(len(scoped), len(result.findings))
        # Inapplicable controls never appear in a section's status or counts.
        out = {f.control_id for f in result.findings if not f.in_scope and not f.unresolved}
        for name, section in result.sections().items():
            self.assertFalse(out & set(section["conflicts"] + section["additions"]), name)

    def test_ledger_is_content_addressed_and_reproducible(self):
        doc = _read("policy_conforming.txt")
        result = review(self.rs, self.water, self.facts, doc, KeywordExtractor())
        first = build_ledger(self.rs, result, doc, "policy_conforming.txt", "keyword-baseline")
        second = build_ledger(self.rs, result, doc, "policy_conforming.txt", "keyword-baseline")
        self.assertEqual(first["document"]["sha256"], second["document"]["sha256"])
        self.assertEqual(first["sections"], second["sections"])
        self.assertEqual(len(first["ledger_sha256"]), 64)

    def test_advisory_controls_are_annotated_not_hidden(self):
        result = review(self.rs, self.city, self.facts, _read("policy_deficient.txt"), KeywordExtractor())
        finding = self._finding(result, "TX-PFIA-2256.023-d-001")
        self.assertTrue(finding.advisory_only)



class TestScopeRealignment(unittest.TestCase):
    """ADR 0011: Core reviewed in full; Context summarized; GTOT paused."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.city = _json(BASE / "data" / "profiles" / "city.json")
        cls.facts = _json(FIX / "facts_water_authority.json")
        cls.doc = _read("policy_deficient.txt")
        cls.summary = review(cls.rs, cls.city, cls.facts, cls.doc, KeywordExtractor())
        cls.full = review(cls.rs, cls.city, cls.facts, cls.doc, KeywordExtractor(), context_depth="FULL")

    def test_context_is_one_line_in_the_governance_summary(self):
        for f in self.summary.findings:
            if self.rs.control(f.control_id).relevance == "CONTEXT":
                self.assertEqual(f.section, "POLICY_GOVERNANCE", f.control_id)
                if f.in_scope:
                    self.assertIn(f.status, ("ALIGNED", "NOT_ADDRESSED"), f.control_id)
                    self.assertIsNone(f.advisory_status)

    def test_context_never_sets_a_section_status(self):
        pfia = self.summary.disposition("PFIA_REQUIREMENTS")
        context = {c.control_id for c in self.rs.controls if c.relevance == "CONTEXT"}
        self.assertFalse(context & set(pfia["conflicts"] + pfia["additions"]))

    def test_core_is_reviewed_identically_at_either_depth(self):
        s = {f.control_id: (f.status, f.verdict) for f in self.summary.findings}
        f_ = {f.control_id: (f.status, f.verdict) for f in self.full.findings}
        for c in self.rs.controls:
            if c.relevance == "CORE":
                self.assertEqual(s[c.control_id], f_[c.control_id], c.control_id)

    def test_full_depth_restores_the_full_scope_review(self):
        self.assertNotIn("POLICY_GOVERNANCE", self.full.sections())
        f = next(x for x in self.full.findings if x.control_id == "TX-PFIA-2256.005-f-001")
        self.assertEqual(f.section, "PFIA_REQUIREMENTS")

    def test_gtot_is_paused_and_absent(self):
        self.assertFalse(any(r.authority == "GTOT" for r in self.rs.registers))
        self.assertNotIn("GTOT", self.summary.sections())

    def test_quarterly_reporting_is_core(self):
        for cid in ("TX-PFIA-2256.023-a-001", "TX-PFIA-2256.023-b-001"):
            self.assertEqual(self.rs.control(cid).relevance, "CORE")


if __name__ == "__main__":
    unittest.main()


class TestScoringBands(unittest.TestCase):
    """The advisory band must never leak into the statutory index."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.city = _json(BASE / "data" / "profiles" / "city.json")
        cls.facts = _json(FIX / "facts_water_authority.json")
        cls.doc = _read("policy_deficient.txt")
        cls.result = review(cls.rs, cls.city, cls.facts, cls.doc, KeywordExtractor())

    def test_bands_partition_the_applicable_set(self):
        from pfia.evaluate import ADVISORY, STATUTORY

        statutory = self.result.in_scope(STATUTORY)
        advisory = self.result.in_scope(ADVISORY)
        self.assertEqual(len(statutory) + len(advisory), len(self.result.in_scope()))
        self.assertTrue(statutory and advisory)

    def test_element_level_band_splits_a_mixed_control(self):
        full = review(self.rs, self.city, self.facts, self.doc, KeywordExtractor(), context_depth="FULL")
        finding = next(f for f in full.findings if f.control_id == "TX-PFIA-2256.005-f-001")
        bands = {e.element_id: e.band for e in finding.elements}
        self.assertEqual(bands["e1a"], "STATUTORY")
        self.assertEqual(bands["e2"], "ADVISORY")
        self.assertEqual(finding.band, "STATUTORY")
        if finding.status != "CONFLICTS":
            self.assertIsNotNone(finding.advisory_status)

    def test_band_follows_policy_text_expectation(self):
        from pfia.evaluate import ADVISORY, STATUTORY

        by_id = {f.control_id: f for f in self.result.findings}
        self.assertEqual(by_id["TX-PFIA-2256.005-b-4-A-001"].band, STATUTORY)   # REQUIRED
        self.assertEqual(by_id["TX-PFIA-2256.005-l-001"].band, STATUTORY)       # RECOMMENDED
        self.assertEqual(by_id["TX-PFIA-2256.023-a-001"].band, ADVISORY)        # NOT_REQUIRED

    def test_no_index_or_weight_survives(self):
        """ADR 0010: statuses only. No composite, weight or score on any object."""
        for f in self.result.findings:
            self.assertFalse(hasattr(f, "score") or hasattr(f, "weight"), f.control_id)
        self.assertFalse(hasattr(self.result, "compliance_index"))
        ledger = build_ledger(self.rs, self.result, self.doc, "policy_deficient.txt", "keyword-baseline")
        self.assertNotIn("scores", ledger)
        text = __import__("json").dumps(ledger)
        for word in ('"composite"', '"weight"', '"score"'):
            self.assertNotIn(word, text)

    def test_advisory_misses_never_become_critical_failures(self):
        from pfia.evaluate import ADVISORY

        advisory_ids = {f.control_id for f in self.result.in_scope(ADVISORY)}
        driving = set()
        for section in self.result.sections().values():
            driving |= set(section["conflicts"] + section["additions"])
        self.assertFalse(advisory_ids & driving)

    def test_ledger_reports_both_indices(self):
        ledger = build_ledger(self.rs, self.result, self.doc, "policy_deficient.txt", "keyword-baseline")
        # ADR 0011: the firm's business first; governance summarized; GTOT paused, so absent.
        self.assertEqual(list(ledger["sections"]), ["AUTHORIZED_INVESTMENTS", "PFIA_REQUIREMENTS", "POLICY_GOVERNANCE"])
        pfia = ledger["sections"]["PFIA_REQUIREMENTS"]
        self.assertEqual(pfia["status"], "REVISIONS_RECOMMENDED")
        self.assertIn("REQUIRED_CONTENT", pfia["counts"])
        self.assertIn("COMMONLY_RESTATED", pfia["counts"])
        self.assertEqual(ledger["sections"]["POLICY_GOVERNANCE"]["status"], "SUMMARIZED")

    def test_blanket_incorporation_is_caught(self):
        by_id = {f.control_id: f for f in self.result.findings}
        listing = by_id["TX-PFIA-2256.005-b-4-A-001"]
        self.assertEqual(listing.verdict, "DEFICIENT")
        self.assertTrue(listing.anti_pattern_hits)

    def test_prudent_investor_language_is_caught(self):
        by_id = {f.control_id: f for f in self.result.findings}
        self.assertTrue(by_id["TX-PFIA-2256.006-a-001"].anti_pattern_hits)

    def test_grandfathering_misread_is_caught(self):
        by_id = {f.control_id: f for f in self.result.findings}
        self.assertTrue(by_id["TX-PFIA-2256.021-001"].anti_pattern_hits)


class TestAbsentVersusDeficient(unittest.TestCase):
    """An anti-pattern hit means the policy speaks wrongly, not that it is silent."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.city = _json(BASE / "data" / "profiles" / "city.json")
        cls.result = review(cls.rs, cls.city, _json(FIX / "facts_deposit_program.json"),
                            _read("policy_deficient.txt"), KeywordExtractor())

    def _finding(self, control_id):
        return next(f for f in self.result.findings if f.control_id == control_id)

    def test_zero_score_with_anti_pattern_is_deficient_not_absent(self):
        finding = self._finding("IS-2256.010-b-001")
        self.assertTrue(finding.anti_pattern_hits)
        self.assertEqual(finding.verdict, "DEFICIENT")
        self.assertEqual(finding.status, "CONFLICTS")
        self.assertTrue(any("non-conforming terms" in r for r in finding.reasons))

    def test_true_silence_remains_absent(self):
        """Tested on a control that genuinely requires affirmative policy text.

        A Schedule B conformity control is satisfied by silence by design - a policy that
        names an instrument and says nothing further conflicts with nothing - so silence
        there is CONFORMING, and the restatement gap sits in the advisory companion.
        Sec. 2256.005(e) is different: the statute requires the policy to say it.
        """
        result = review(self.rs, self.city, _json(FIX / "facts_deposit_program.json"),
                        "This document says nothing relevant.", KeywordExtractor())
        finding = next(f for f in result.findings
                       if f.control_id == "TX-PFIA-2256.005-e-001")
        self.assertFalse(finding.anti_pattern_hits)
        self.assertEqual(finding.verdict, "ABSENT")

    def test_a_conformity_control_is_satisfied_by_silence(self):
        """The counterpart, stated as behaviour rather than left implicit."""
        result = review(self.rs, self.city, _json(FIX / "facts_deposit_program.json"),
                        "Brokered certificates of deposit are authorized.", KeywordExtractor())
        finding = next(f for f in result.findings if f.control_id == "IS-2256.010-b-001")
        self.assertEqual(finding.verdict, "CONFORMING")
        completeness = next(f for f in result.findings if f.control_id == "IS-2256.010-b-002")
        self.assertEqual(completeness.band, "ADVISORY")


class TestNegativeElements(unittest.TestCase):
    """Elements that limit what a policy may say, rather than require what it must.

    A policy that settles everything DVP with no carve-out at all satisfies
    Sec. 2256.005(b)(4)(E) perfectly, and has no passage to quote for "any carve-out is
    limited to pool and mutual funds". Demanding an affirmative span there fails the
    best-drafted policies, and it was the largest single source of spurious PARTIAL
    verdicts on a real document.
    """

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.water = _json(BASE / "data" / "profiles" / "water_authority.json")
        cls.facts = _json(FIX / "facts_water_authority.json")

    def _run(self, document):
        from pfia.adapter import run_extraction
        from pfia.adapter.providers import ReplayAdapter

        cassette = {"TX-PFIA-2256.005-b-4-E-001": {"elements": [
            {"id": "e1", "supported": True,
             "quote": "shall be settled on a delivery versus payment basis"}]}}
        run = run_extraction(self.rs, ReplayAdapter(cassette, name="fixture"), document,
                             self.water, self.facts)
        result = review(self.rs, self.water, self.facts, document,
                        PrecomputedExtractor(run.payload, source="fixture"))
        return next(f for f in result.findings
                    if f.control_id == "TX-PFIA-2256.005-b-4-E-001")

    def test_no_carve_out_conforms(self):
        finding = self._run(
            "SETTLEMENT. All securities purchased shall be settled on a delivery versus "
            "payment basis.")
        self.assertEqual(finding.verdict, "CONFORMING")
        satisfied = {e.element_id: e.satisfied for e in finding.elements}
        self.assertTrue(satisfied["e2"])

    def test_a_disqualifying_carve_out_still_fails(self):
        finding = self._run(
            "SETTLEMENT. All securities shall be settled on a delivery versus payment "
            "basis, except where the safekeeping bank determines otherwise.")
        satisfied = {e.element_id: e.satisfied for e in finding.elements}
        self.assertFalse(satisfied["e2"])
        self.assertEqual(finding.verdict, "DEFICIENT")

    def test_negative_elements_carry_a_span_when_contradicted(self):
        finding = self._run(
            "All securities shall be settled on a delivery versus payment basis unless "
            "the Investment Officer directs otherwise.")
        element = next(e for e in finding.elements if e.element_id == "e2")
        self.assertFalse(element.satisfied)
        self.assertTrue(element.spans)

    def test_register_requires_contradicting_language_for_a_negative_element(self):
        for control in self.rs.controls:
            for element in control.elements:
                if element.negative:
                    self.assertTrue(element.contradicted_by, f"{control.control_id}:{element.id}")


class TestConformityAndCompleteness(unittest.TestCase):
    """Naming an instrument without restating its statutory conditions is not a breach.

    Sec. 2256.005(b)(4)(A) requires a list of authorized types; it does not require the
    policy to restate each type's conditions, and Sec. 2256.024 makes those conditions
    bind of their own force. What is a statutory failure is authorizing an instrument on
    terms the statute forbids.
    """

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.profile = _json(BASE / "data" / "profiles" / "water_authority.json")
        cls.facts = {"authorized_instruments": ["BANKERS_ACCEPTANCE"]}

    def _review(self, document):
        return review(self.rs, self.profile, self.facts, document, KeywordExtractor())

    def test_bare_authorization_conforms(self):
        """The NTTA case: an instrument named with a stricter-than-statutory limit."""
        result = self._review(
            "Authorized investments include banker's acceptances with a stated maturity of "
            "180 days or less."
        )
        conformity = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(conformity.band, "STATUTORY")
        self.assertEqual(conformity.verdict, "CONFORMING")

    def test_the_restatement_gap_is_advisory_not_statutory(self):
        result = self._review(
            "Authorized investments include banker's acceptances with a stated maturity of "
            "180 days or less."
        )
        completeness = next(f for f in result.findings if f.control_id == "IS-2256.012-002")
        self.assertEqual(completeness.band, "ADVISORY")
        self.assertNotEqual(completeness.verdict, "CONFORMING")
        section = result.disposition("AUTHORIZED_INVESTMENTS")
        self.assertNotIn(completeness.control_id, section["conflicts"] + section["additions"])

    def _review_with_facts(self, document, facts):
        payload = {"IS-2256.012-001": {"elements_satisfied": {}, "facts": facts}}
        return review(self.rs, self.profile, self.facts, document,
                      PrecomputedExtractor(payload, source="fixture"))

    def test_a_non_conforming_stated_figure_is_still_statutory(self):
        """Caught by comparing numbers, not by matching a string.

        A literal "365 days" cannot tell a looser limit from a stricter one, and policies
        tier their limits routinely - A-1+ paper to 270 days, A-1 paper to 180. Every tier
        below the statutory cap is a narrowing.
        """
        result = self._review_with_facts(
            "Banker's acceptances with a stated maturity of 365 days or less.",
            {"max_maturity_days": 365})
        conformity = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(conformity.verdict, "DEFICIENT")

    def test_a_stricter_stated_figure_conforms_and_says_so(self):
        result = self._review_with_facts(
            "Banker's acceptances with a stated maturity of 180 days or less.",
            {"max_maturity_days": 180})
        conformity = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(conformity.verdict, "CONFORMING")
        self.assertTrue(any("stricter than the statutory limit" in r
                            for r in conformity.reasons))

    def test_tiered_limits_are_judged_on_the_loosest_tier(self):
        """The example the reviewers gave: A-1+ paper to 270 days, A-1 paper to 180.

        Commercial paper is capped at 365 days, so both tiers narrow and the policy
        conforms. The loosest tier - 270 - is the one that has to clear the statute, which
        is why the model is told to report the most permissive figure.
        """
        payload = {"IS-2256.013-001": {"elements_satisfied": {},
                                       "facts": {"max_maturity_days": 270}}}
        result = review(self.rs, self.profile,
                        {"authorized_instruments": ["COMMERCIAL_PAPER"]},
                        "Commercial paper rated A-1+ maturing in 270 days or less; A-1 "
                        "rated paper in 180 days or less.",
                        PrecomputedExtractor(payload, source="fixture"))
        finding = next(f for f in result.findings if f.control_id == "IS-2256.013-001")
        self.assertEqual(finding.verdict, "CONFORMING")
        self.assertTrue(any("stricter than the statutory limit" in r for r in finding.reasons))

    def test_a_stated_conflict_is_deficient_not_absent(self):
        """A figure that exceeds the cap is contradicting evidence, not silence."""
        result = self._review_with_facts(
            "Banker's acceptances with a stated maturity of 365 days or less.",
            {"max_maturity_days": 365})
        finding = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(finding.verdict, "DEFICIENT")
        self.assertTrue(any("stated conflict rather than an omission" in r
                            for r in finding.reasons))

    def test_every_instrument_has_both_controls(self):
        codes = {}
        for control in self.rs.controls:
            if control.schedule != "B" or control.inverted:
                continue
            codes.setdefault(control.instrument_code, set()).add(
                control.policy_text_expectation)
        for code, expectations in codes.items():
            self.assertEqual(expectations, {"REQUIRED", "RECOMMENDED_NOT_REQUIRED"}, code)


class TestIncorporationByReference(unittest.TestCase):
    """"only the following investment types, as further defined by the PFIA, are authorized"

    This is common, deliberate drafting: the list of types is closed, and each type's
    statutory conditions float with the chapter so an amendment does not force a policy
    rewrite. The conditions are in the policy by reference rather than by recitation, so
    the completeness control is met - not excused.
    """

    @classmethod
    def setUpClass(cls):
        from pfia.instruments import detect

        cls.rs = loader.load(ROOT)
        cls.profile = _json(BASE / "data" / "profiles" / "EXAMPLE-tollway-authority.json")
        cls.document = _read("policy_unindented_list.txt")
        cls.facts = detect(cls.rs, cls.document, ROOT).to_facts()
        cls.result = review(cls.rs, cls.profile, cls.facts, cls.document, KeywordExtractor())

    def _finding(self, control_id):
        return next(f for f in self.result.findings if f.control_id == control_id)

    def test_the_clause_is_detected_from_the_stem(self):
        from pfia.instruments import detect

        resolution = detect(self.rs, self.document, ROOT)
        self.assertIsNotNone(resolution.incorporation)
        self.assertTrue(resolution.incorporation["in_stem"])
        self.assertTrue(self.facts["incorporates_statutory_conditions"])

    def test_completeness_is_satisfied_by_reference_not_excused(self):
        finding = self._finding("IS-2256.012-002")
        self.assertEqual(finding.verdict, "CONFORMING")
        self.assertEqual(finding.status, "ALIGNED_BY_REFERENCE")
        self.assertTrue(finding.applicable)
        self.assertTrue(any("by reference" in r for r in finding.reasons))
        for element in finding.elements:
            self.assertEqual(element.basis, "incorporated by reference")

    def test_conformity_is_unaffected(self):
        """Incorporation says the conditions apply. It cannot make a stated figure that
        exceeds the statutory cap conform."""
        payload = {"IS-2256.012-001": {"elements_satisfied": {},
                                       "facts": {"max_maturity_days": 365}}}
        result = review(self.rs, self.profile, self.facts, self.document,
                        PrecomputedExtractor(payload, source="fixture"))
        conformity = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(conformity.verdict, "DEFICIENT")

    def test_schedule_a_content_mandates_are_not_satisfied_by_reference(self):
        """Incorporation cannot supply what the entity must decide for itself.

        The maximum stated maturity, the dollar-weighted average maturity, the pricing
        method and the fund strategies are entity choices, and no reference to the chapter
        answers them.
        """
        for control_id in ("TX-PFIA-2256.005-b-4-B-001", "TX-PFIA-2256.005-b-4-C-001",
                           "TX-PFIA-2256.005-b-4-D-001", "TX-PFIA-2256.005-d-001"):
            control = self.rs.control(control_id)
            effects = {ex.effect for ex in control.exemptions}
            self.assertNotIn("SATISFIED_BY_REFERENCE", effects, control_id)

    def test_a_policy_without_the_clause_still_shows_the_advisory_gap(self):
        """Written as a fresh document rather than by editing the fixture: the fixture wraps
        the clause across a line, so a naive string replacement leaves it in place."""
        from pfia.instruments import detect

        document = (
            "AUTHORIZED INVESTMENTS.\n\nOnly the following investment types are "
            "authorized:\n\n"
            "(a) Banker's acceptances with a stated maturity of 180 days or less.\n\n"
            "(b) Commercial paper rated A-1/P-1 with a stated maturity of 270 days or "
            "less.\n"
        )
        facts = detect(self.rs, document, ROOT).to_facts()
        self.assertFalse(facts["incorporates_statutory_conditions"])
        result = review(self.rs, self.profile, facts, document, KeywordExtractor())
        completeness = next(f for f in result.findings if f.control_id == "IS-2256.012-002")
        self.assertNotEqual(completeness.verdict, "CONFORMING")
        self.assertEqual(completeness.band, "ADVISORY")
        conformity = next(f for f in result.findings if f.control_id == "IS-2256.012-001")
        self.assertEqual(conformity.verdict, "CONFORMING")

    def test_an_item_level_clause_is_recorded_but_not_generalised(self):
        """A clause inside one item governs that item, not the schedule."""
        from pfia.instruments import detect

        document = (
            "AUTHORIZED INVESTMENTS.\n\nOnly the following investment types are "
            "authorized:\n\n"
            "(a) Banker's acceptances with a stated maturity of 180 days or less.\n\n"
            "(b) Texas local government investment pools as described by the PFIA and "
            "authorized by the Board.\n"
        )
        resolution = detect(self.rs, document, ROOT)
        self.assertIsNotNone(resolution.incorporation)
        self.assertEqual(resolution.incorporation["scope"], "item")
        self.assertFalse(resolution.incorporation["applies"])
        self.assertFalse(resolution.to_facts()["incorporates_statutory_conditions"])

    def test_incorporation_is_not_blanket_incorporation(self):
        """One closes the set of types and floats the conditions; the other leaves the set
        open and fails Sec. 2256.005(b)(4)(A)."""
        from pfia.instruments import detect

        resolution = detect(self.rs, self.document, ROOT)
        self.assertEqual(resolution.state, "enumerated")
        self.assertFalse(resolution.unresolved)
        blanket = detect(self.rs, _read("policy_deficient.txt"), ROOT)
        self.assertEqual(blanket.state, "blanket_incorporation")
        self.assertIsNone(blanket.incorporation)
