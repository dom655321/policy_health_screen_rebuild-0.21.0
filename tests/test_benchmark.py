"""Ground-truth comparison.

The synthetic ground truth is hand-authored from the fixture and includes a deliberate
disagreement. It exercises the comparison paths; it measures nothing.
"""

import json
import unittest
from pathlib import Path

from pfia import coverage as coverage_module
from pfia import loader, profile as profile_module
from pfia.benchmark import (
    GroundTruthError, ISSUE_RAISED, compare, load_ground_truth, normalize_verdict, summarize,
)
from pfia.evaluate import review
from pfia.extraction import KeywordExtractor
from pfia.ingest import ingest_path
from pfia.instruments import detect
from pfia.ledger import build_ledger

BASE = Path(__file__).resolve().parents[1]
REGISTERS = BASE / "data" / "registers"
PROFILES = BASE / "data" / "profiles"
TRUTH = BASE / "tests" / "ground-truth" / "synthetic-deficient.json"


def _ledger(rs):
    source = ingest_path(BASE / "tests" / "fixtures" / "policy_deficient.txt", backend="plaintext")
    entity, report = profile_module.load(rs, PROFILES / "city.json", PROFILES)
    resolution = detect(rs, source.text, REGISTERS)
    result = review(rs, entity, resolution.to_facts(), source.text, KeywordExtractor())
    return build_ledger(
        rs, result, source.text, "policy_deficient.txt", "keyword-baseline", source=source,
        coverage=coverage_module.build(rs, REGISTERS, entity["classes"]),
        profile_report=report, instruments=resolution,
    )


class TestVerdictMapping(unittest.TestCase):
    def test_reviewer_vocabulary_maps_onto_the_register(self):
        for word, expected in [("Pass", "CONFORMING"), ("Partial", "DEFICIENT"),
                               ("Not Found", "ABSENT"), ("N/A", "NOT_APPLICABLE"),
                               ("non-compliant", "DEFICIENT")]:
            self.assertEqual(normalize_verdict(word), expected)

    def test_unknown_verdict_is_refused_not_guessed(self):
        with self.assertRaises(GroundTruthError):
            normalize_verdict("mostly fine")

    def test_issue_set_covers_both_failure_verdicts(self):
        self.assertEqual(ISSUE_RAISED, {"DEFICIENT", "ABSENT"})


class TestComparison(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.ledger = _ledger(cls.rs)
        cls.truth = load_ground_truth(TRUTH)
        cls.result = compare(cls.ledger, cls.truth,
                             {c.control_id for c in cls.rs.controls})

    def test_every_reviewed_control_is_compared_or_explained(self):
        accounted = (
            self.result.compared + len(self.result.reviewer_scored_unresolved)
        )
        self.assertEqual(accounted, len(self.truth["findings"]))

    def test_the_deliberate_disagreement_is_caught(self):
        by_id = {d.control_id: d for d in self.result.disagreements}
        self.assertIn("TX-PFIA-2256.005-b-2-001", by_id)
        self.assertEqual(by_id["TX-PFIA-2256.005-b-2-001"].kind, "false_issue")

    def test_disagreements_carry_the_evidence_relied_on(self):
        for disagreement in self.result.disagreements:
            self.assertTrue(disagreement.model_reasons or disagreement.model_spans)
            self.assertTrue(disagreement.citation)

    def test_unmapped_reviewer_findings_are_preserved(self):
        self.assertEqual(len(self.result.unmapped_findings), 1)
        self.assertIn("2256.016", self.result.unmapped_findings[0]["section"])

    def test_controls_the_reviewer_did_not_address_are_listed_not_scored(self):
        self.assertTrue(self.result.unreviewed_controls)
        self.assertFalse(set(self.result.unreviewed_controls) & set(self.truth["findings"]))

    def test_unknown_control_id_is_rejected(self):
        broken = dict(self.truth)
        broken["findings"] = dict(self.truth["findings"])
        broken["findings"]["TX-PFIA-9999.999-001"] = {"verdict": "Pass", "note": ""}
        with self.assertRaises(GroundTruthError):
            compare(self.ledger, broken, {c.control_id for c in self.rs.controls})

    def test_detection_counts_reconcile_with_comparisons(self):
        detection = self.result.detection
        self.assertEqual(sum(detection.values()), self.result.compared)

    def test_summary_reports_precision_and_recall(self):
        summary = summarize([self.result])
        self.assertEqual(summary["cases"], 1)
        self.assertIsNotNone(summary["recall"])
        self.assertIn("Unmapped reviewer findings", summary["note"])


if __name__ == "__main__":
    unittest.main()
