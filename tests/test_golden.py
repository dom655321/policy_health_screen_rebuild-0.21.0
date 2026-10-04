"""Golden fixture cases.

Each case pins the whole pipeline for one policy. A failure here is a report to read, not
a test to silence: the diff names every control whose verdict moved.
"""

import json
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))

from golden import GOLDEN, diff, snapshot  # noqa: E402


def _cases():
    return sorted(p for p in GOLDEN.iterdir() if (p / "case.json").exists())


class TestGoldenCases(unittest.TestCase):
    def test_cases_exist(self):
        self.assertGreaterEqual(len(_cases()), 3)

    def test_no_drift(self):
        for case_dir in _cases():
            with self.subTest(case=case_dir.name):
                expected_path = case_dir / "expected.json"
                self.assertTrue(expected_path.exists(), f"{case_dir.name} has no expectation")
                expected = json.loads(expected_path.read_text(encoding="utf-8"))
                lines = diff(expected, snapshot(case_dir))
                self.assertEqual(lines, [], "\n" + "\n".join(lines))

    def test_cases_are_deterministic(self):
        case_dir = _cases()[0]
        self.assertEqual(snapshot(case_dir), snapshot(case_dir))


if __name__ == "__main__":
    unittest.main()


class TestIngestionNeutrality(unittest.TestCase):
    """The delivery format must not move a single verdict.

    The same policy is pinned twice: once as text, once as a PDF read by the
    zero-dependency backend after dehyphenation and running-head removal. If these ever
    diverge, ingestion is losing or inventing policy language.
    """

    def _expected(self, name):
        return json.loads((GOLDEN / name / "expected.json").read_text(encoding="utf-8"))

    def test_pdf_case_matches_the_text_case(self):
        text = self._expected("water-authority-conforming")
        pdf = self._expected("water-authority-pdf")
        self.assertNotEqual(text["ingest"]["backend"], pdf["ingest"]["backend"])
        self.assertEqual(text["sections"], pdf["sections"])
        self.assertEqual(text["statuses"], pdf["statuses"])

    def test_pdf_case_actually_exercised_the_hard_paths(self):
        transforms = self._expected("water-authority-pdf")["ingest"]["transforms"]
        self.assertGreaterEqual(transforms.get("line_break_hyphens_joined", 0), 1)
        self.assertGreater(transforms.get("running_heads_removed", 0), 0)
