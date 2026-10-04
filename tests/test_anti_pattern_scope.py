"""Anti-pattern scope: document-wide by default, anchored for generic qualifiers (EA-2026-09-27)."""
import unittest
from pathlib import Path

from pfia import loader
from pfia.adapter.payload import anti_pattern_hits, negative_element_results

BASE = Path(__file__).resolve().parents[1]
RS = loader.load(BASE / "data" / "registers")
CTL = {c.control_id: c for c in RS.controls}
DEFICIENT = (BASE / "tests" / "fixtures" / "policy_deficient.txt").read_text(encoding="utf-8")


class TestAnchors(unittest.TestCase):
    def test_generic_qualifier_about_another_subject_is_ignored(self):
        # "Ratings will be reviewed as needed" is about ratings, not the policy review.
        hits = anti_pattern_hits(CTL["TX-PFIA-2256.005-e-001"], DEFICIENT)
        matched = [DEFICIENT[s:e].lower() for s, e in hits]
        self.assertNotIn("reviewed as needed", matched)

    def test_generic_qualifier_about_the_subject_still_fires(self):
        hits = anti_pattern_hits(CTL["TX-PFIA-2256.005-e-001"], DEFICIENT)
        self.assertIn("reviewed periodically", [DEFICIENT[s:e].lower() for s, e in hits])

    def test_deficient_language_without_statutory_wording_is_still_caught(self):
        # Window scoping lost these; document-wide matching must keep them.
        for cid in ("IS-2256.010-b-001", "IS-2256.009-a-8-001", "TX-PFIA-2256.005-l-001", "TX-PFIA-2256.006-a-001"):
            self.assertTrue(anti_pattern_hits(CTL[cid], DEFICIENT), cid)

    def test_speculation_disclaimer_does_not_trip_hedging(self):
        doc = "Objectives. Investments shall not be made for speculation or speculative purposes."
        self.assertEqual(anti_pattern_hits(CTL["IS-2256.0201-001"], doc), [])
        self.assertTrue(anti_pattern_hits(CTL["IS-2256.0201-001"], "Hedging transactions may be speculative."))

    def test_negative_elements_follow_the_same_anchors(self):
        doc = "Pools are rated at the time of investment."
        res = negative_element_results(CTL["IS-2256.019-001"], doc)
        self.assertIn(False, res["elements_satisfied"].values())
        res = negative_element_results(CTL["IS-2256.019-001"], "Commercial paper must be rated at the time of investment.")
        self.assertNotIn(False, res["elements_satisfied"].values())

    def test_removed_patterns_are_gone(self):
        gone = {"TX-PFIA-2256.008-a1-001": "annually", "TX-PFIA-2256.005-i-001": "filed with the governing body",
                "IS-2256.020-3-001": "AA-", "IS-2256.020-2-001": "insured by the Federal Deposit Insurance Corporation"}
        for cid, pat in gone.items():
            self.assertNotIn(pat, CTL[cid].test.get("anti_patterns", []) or [], cid)


if __name__ == "__main__":
    unittest.main()
