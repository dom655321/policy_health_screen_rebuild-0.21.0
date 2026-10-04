"""0.21.0: the rebuilt screen report, kerned-fragment repair, and reliability guards."""
import json
import re
import unittest
from pathlib import Path

from pfia.ingest.backends.stdlib_pdf import _content_text
from pfia.ingest.quality import assess, word_split_artifacts
from pfia.report.outputs import (BLOCKS, UNDETERMINED, _to_days, authorization_reliability, load_strategy,
                                 mandate_fit_context, redline_context, screen_context)
from pfia.report.phrasing import scrub_check

BASE = Path(__file__).resolve().parents[1]
REG = BASE / "data" / "registers"
STRATEGY = BASE / "data" / "mandates" / "short-term-government-credit.example.json"


def _example_ledger():
    import sys
    sys.path.insert(0, str(BASE / "scripts"))
    import make_output_examples as m
    return m.example_ledger("policy_deficient.txt", "city", "facts_deposit_program.json")


class TestKernedFragments(unittest.TestCase):
    def test_same_line_fragments_join_into_words(self):
        stream = (b"BT /F1 12 Tf 72 700 Td (Not less than q) Tj 50 0 Td (uarter) Tj 30 0 Td (ly the) Tj "
                  b"20 0 Td (Officer) Tj 25 0 Td (, assisted by the) Tj 0 -14 Td (T) Tj 6 0 Td (he County) Tj "
                  b"40 0 Td (transaction) Tj 40 0 Td (s) Tj 10 0 Td (and the policy) Tj ET")
        text = _content_text(stream)
        self.assertIn("quarterly the Officer, assisted", text)
        self.assertIn("The County transactions and the policy", text)

    def test_a_real_line_move_still_breaks_the_line(self):
        text = _content_text(b"BT 72 700 Td (first line) Tj 0 -14 Td (second line) Tj ET")
        self.assertEqual(text.strip().split("\n"), ["first line", "second line"])

    def test_split_words_degrade_quality_with_a_remedy(self):
        body = ("Not less than q uarter ly the transaction s of the County. T he report covers all funds. " * 20)
        q = assess(body, [body] * 3)
        self.assertEqual(q.verdict, "DEGRADED")
        self.assertTrue(any("pypdf" in r for r in q.reasons))

    def test_clean_fixtures_are_not_flagged(self):
        for f in (BASE / "tests" / "fixtures").glob("policy_*.txt"):
            self.assertLess(word_split_artifacts(f.read_text(encoding="utf-8")), 5, f.name)


class TestScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = _example_ledger()
        cls.ctx = screen_context(cls.ledger, REG, "City of Example")

    def test_section_order_and_governance_summary(self):
        self.assertEqual([t["label"] for t in self.ctx["tiles"]],
                         ["Authorized investments", "Investment management provisions", "Policy governance (summary)"])

    def test_context_items_never_lead_or_get_cards(self):
        context_ids = {f["control_id"] for f in self.ledger["findings"] if f.get("relevance") == "CONTEXT"}
        self.assertFalse(context_ids & {i["ids"] for i in self.ctx["leading"]})
        self.assertFalse(context_ids & {c["id"] for c in self.ctx["core_cards"]})

    def test_instrument_conflicts_lead_by_condition(self):
        self.assertTrue(any(i["ids"] == "BCD-04" for i in self.ctx["leading"] + []) or
                        any(c["id"] == "BCD-04" for r in self.ctx["v2"] for c in r["conditions"]))

    @unittest.skipUnless(__import__("importlib").util.find_spec("jinja2"), "jinja2 not installed")
    def test_whole_document_has_no_audit_vocabulary(self):
        from pfia.report import render_html
        html = render_html(self.ctx, "screen.html").replace("policy_deficient", "policy_sample")
        text = re.sub(r"<[^>]+>", " ", html)
        self.assertEqual(scrub_check(text), [])
        self.assertNotIn("HSAM", text)


class TestReliabilityGuards(unittest.TestCase):
    def test_unread_authorized_list_is_undetermined_not_blocked(self):
        ledger = _example_ledger()
        ledger["document"]["quality"] = {"verdict": "DEGRADED", "reasons": ["word-splitting artifacts"]}
        self.assertTrue(authorization_reliability(ledger))
        from pfia.conditions import load_catalogue
        cat = load_catalogue(REG / "instrument-conditions" / "register.json")
        ctx = mandate_fit_context(ledger, load_strategy(STRATEGY, cat), REG, "X")
        self.assertNotIn(BLOCKS, [r["fit"] for r in ctx["rows"]])
        self.assertIn(UNDETERMINED, [r["fit"] for r in ctx["rows"]])
        self.assertTrue(redline_context(ledger, REG, "X")["reliability"])

    def test_durations_compare_across_units(self):
        self.assertLess(_to_days(365, "days"), _to_days(3, "years"))
        self.assertIsNone(_to_days(5, "pct_of_fund_assets"))


if __name__ == "__main__":
    unittest.main()
