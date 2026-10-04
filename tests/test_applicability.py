"""Applicability gating is tested in isolation with the NullExtractor.

These are the findings that must never regress: an entity is scored only against the
controls the legislature actually pointed at it.
"""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import NOT_APPLICABLE, review
from pfia.extraction import NullExtractor

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "data" / "registers"


def _profile(name):
    return json.loads((BASE / "data" / "profiles" / f"{name}.json").read_text())


def _facts(name):
    return json.loads((BASE / "tests" / "fixtures" / f"{name}.json").read_text())


class TestApplicability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)

    def _finding(self, result, control_id):
        return next(f for f in result.findings if f.control_id == control_id)

    def test_water_district_is_outside_section_2256_008(self):
        result = review(self.rs, _profile("water_authority"), _facts("facts_water_authority"), "", NullExtractor())
        finding = self._finding(result, "TX-PFIA-2256.008-a-2-001")
        self.assertEqual(finding.verdict, NOT_APPLICABLE)
        self.assertFalse(finding.in_scope)

    def test_municipality_routes_to_the_eight_hour_substitute(self):
        result = review(self.rs, _profile("city"), _facts("facts_water_authority"), "", NullExtractor())
        ten_hour = self._finding(result, "TX-PFIA-2256.008-a-2-001")
        self.assertEqual(ten_hour.verdict, NOT_APPLICABLE)
        self.assertIn("TX-PFIA-2256.008-a1-001", ten_hour.substitutes)
        self.assertTrue(self._finding(result, "TX-PFIA-2256.008-a1-001").applicable)

    def test_isd_corporate_bond_control_is_class_restricted(self):
        facts = {"authorized_instruments": ["ISD_CORPORATE_BOND"]}
        isd = review(self.rs, _profile("isd"), facts, "", NullExtractor())
        city = review(self.rs, _profile("city"), facts, "", NullExtractor())
        self.assertTrue(self._finding(isd, "IS-2256.0204-001").applicable)
        self.assertFalse(self._finding(city, "IS-2256.0204-001").applicable)

    def test_instrument_controls_are_silent_when_not_authorized(self):
        result = review(self.rs, _profile("city"), {"authorized_instruments": ["US_OBLIGATIONS"]}, "", NullExtractor())
        finding = self._finding(result, "IS-2256.013-001")
        self.assertEqual(finding.verdict, NOT_APPLICABLE)
        self.assertIn("not activated", finding.reasons[0])

    def test_safe_harbor_deactivates_auditor_review_control(self):
        result = review(self.rs, _profile("city"), _facts("facts_safe_harbor"), "", NullExtractor())
        self.assertFalse(self._finding(result, "TX-PFIA-2256.023-d-001").in_scope)

    def test_prohibited_instrument_conforming_when_absent(self):
        result = review(self.rs, _profile("city"), {"authorized_instruments": ["US_OBLIGATIONS"]}, "", NullExtractor())
        finding = self._finding(result, "IS-2256.009-b-001")
        self.assertEqual(finding.verdict, "CONFORMING")
        self.assertEqual(finding.status, "ALIGNED")

    def test_prohibited_instrument_deficient_when_authorized(self):
        result = review(self.rs, _profile("city"), {"authorized_instruments": ["CMO_IO_PO_INVERSE"]}, "", NullExtractor())
        finding = self._finding(result, "IS-2256.009-b-001")
        self.assertEqual(finding.verdict, "DEFICIENT")
        self.assertEqual(finding.severity, "CRITICAL")

    def test_subchapter_exclusion_disables_the_whole_register(self):
        profile = _profile("city")
        profile["exclusions"]["public_retirement_system_802_001"] = True
        result = review(self.rs, profile, _facts("facts_water_authority"), "", NullExtractor())
        self.assertEqual(len(result.in_scope()), 0)
        # Not assessed, never a clean result: a clean section over zero controls reads as
        # a clean bill of health for an entity nothing was reviewed against.
        for section in result.sections().values():
            self.assertEqual(section["status"], "NOT_ASSESSED")


if __name__ == "__main__":
    unittest.main()


class TestNewBlockGating(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)

    def _finding(self, result, control_id):
        return next(f for f in result.findings if f.control_id == control_id)

    def test_state_agency_audit_control_is_class_restricted(self):
        facts = _facts("facts_water_authority")
        state = review(self.rs, _profile("state_agency"), facts, "", NullExtractor())
        city = review(self.rs, _profile("city"), facts, "", NullExtractor())
        self.assertTrue(self._finding(state, "TX-PFIA-2256.005-n-001").applicable)
        self.assertFalse(self._finding(city, "TX-PFIA-2256.005-n-001").applicable)
        self.assertFalse(self._finding(state, "TX-PFIA-2256.005-m-001").applicable)
        self.assertTrue(self._finding(city, "TX-PFIA-2256.005-m-001").applicable)

    def test_comptroller_exemption_disables_state_agency_audit(self):
        profile = _profile("state_agency")
        profile["assets_invested_by_comptroller_404_024"] = True
        result = review(self.rs, profile, _facts("facts_water_authority"), "", NullExtractor())
        finding = self._finding(result, "TX-PFIA-2256.005-n-001")
        self.assertEqual(finding.verdict, NOT_APPLICABLE)
        self.assertIn("2256.005(o)", finding.reasons[0])

    def test_officer_assigned_by_law_disables_designation_control(self):
        profile = _profile("city")
        profile["investment_function_assigned_by_law"] = True
        result = review(self.rs, profile, _facts("facts_water_authority"), "", NullExtractor())
        self.assertEqual(self._finding(result, "TX-PFIA-2256.005-f-001").verdict, NOT_APPLICABLE)

    def test_dwam_control_requires_a_pooled_fund_group(self):
        profile = _profile("city")
        profile["has_pooled_fund_groups"] = False
        result = review(self.rs, profile, _facts("facts_water_authority"), "", NullExtractor())
        self.assertFalse(self._finding(result, "TX-PFIA-2256.005-b-4-C-001").applicable)

    def test_rating_control_needs_a_rated_instrument(self):
        unrated = {"authorized_instruments": ["US_OBLIGATIONS", "DEPOSITORY_CD"]}
        rated = {"authorized_instruments": ["US_OBLIGATIONS", "COMMERCIAL_PAPER"]}
        a = review(self.rs, _profile("city"), unrated, "", NullExtractor())
        b = review(self.rs, _profile("city"), rated, "", NullExtractor())
        self.assertFalse(self._finding(a, "TX-PFIA-2256.021-001").applicable)
        self.assertTrue(self._finding(b, "TX-PFIA-2256.021-001").applicable)

    def test_interpretive_control_only_reaches_391_commissions(self):
        result = review(self.rs, _profile("city"), _facts("facts_water_authority"), "", NullExtractor())
        self.assertFalse(self._finding(result, "TX-PFIA-2256.005-h-001").applicable)


class TestInstrumentScheduleGating(unittest.TestCase):
    """Schedule B activation is driven solely by the policy's own authorized list."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.profile = _profile("city")

    def _finding(self, result, control_id):
        return next(f for f in result.findings if f.control_id == control_id)

    def test_deposit_controls_activate_independently(self):
        direct = review(self.rs, self.profile, {"authorized_instruments": ["INTEREST_BEARING_DEPOSIT"]}, "", NullExtractor())
        self.assertTrue(self._finding(direct, "IS-2256.009-a-7-001").applicable)
        self.assertFalse(self._finding(direct, "IS-2256.009-a-8-001").applicable)

        placed = review(self.rs, self.profile, {"authorized_instruments": ["BROKERED_DEPOSIT"]}, "", NullExtractor())
        self.assertFalse(self._finding(placed, "IS-2256.009-a-7-001").applicable)
        self.assertTrue(self._finding(placed, "IS-2256.009-a-8-001").applicable)

    def test_brokered_deposit_and_brokered_cd_are_separate_controls(self):
        result = review(self.rs, self.profile, _facts("facts_deposit_program"), "", NullExtractor())
        deposit = self._finding(result, "IS-2256.009-a-8-001")
        cd = self._finding(result, "IS-2256.010-b-001")
        self.assertTrue(deposit.applicable and cd.applicable)
        self.assertNotEqual(deposit.citation, cd.citation)
        self.assertEqual(deposit.citation, "Sec. 2256.009(a)(8)")
        self.assertEqual(cd.citation, "Sec. 2256.010(b)")

    def test_direct_cd_control_is_independent_of_the_brokered_one(self):
        result = review(self.rs, self.profile, {"authorized_instruments": ["DEPOSITORY_CD"]}, "", NullExtractor())
        self.assertTrue(self._finding(result, "IS-2256.010-a-001").applicable)
        self.assertFalse(self._finding(result, "IS-2256.010-b-001").applicable)

    def test_reverse_repo_control_needs_its_own_authorization(self):
        repo_only = review(self.rs, self.profile, {"authorized_instruments": ["REPO"]}, "", NullExtractor())
        self.assertTrue(self._finding(repo_only, "IS-2256.011-001").applicable)
        self.assertFalse(self._finding(repo_only, "IS-2256.011-c-001").applicable)

    def test_pool_authorization_activates_both_pool_controls(self):
        result = review(self.rs, self.profile, {"authorized_instruments": ["INVESTMENT_POOL"]}, "", NullExtractor())
        self.assertTrue(self._finding(result, "IS-2256.016-001").applicable)
        self.assertTrue(self._finding(result, "IS-2256.019-001").applicable)

    def test_each_instrument_carries_a_statutory_and_an_advisory_control(self):
        """Conformity is statutory; restating the conditions is advisory.

        Sec. 2256.005(b)(4)(A) requires a list of authorized types, not a restatement of
        each type's statutory conditions, and Sec. 2256.024 makes those conditions bind of
        their own force. Demanding the restatement as a statutory element failed policies
        that had violated nothing.
        """
        from pfia.evaluate import ADVISORY, STATUTORY

        result = review(self.rs, self.profile, _facts("facts_deposit_program"), "", NullExtractor())
        bands: dict[str, set[str]] = {}
        for finding in result.findings:
            if finding.schedule != "B":
                continue
            control = self.rs.control(finding.control_id)
            if control.inverted:
                self.assertEqual(finding.band, STATUTORY)
                continue
            bands.setdefault(control.instrument_code, set()).add(finding.band)
        self.assertTrue(bands)
        for code, seen in bands.items():
            self.assertEqual(seen, {STATUTORY, ADVISORY}, code)
