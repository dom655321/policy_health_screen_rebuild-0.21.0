"""Redline and mandate-fit outputs built from a finding ledger."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pfia import loader
from pfia.adapter import run_extraction
from pfia.adapter.providers import HeuristicAdapter
from pfia.conditions import load_catalogue, wiring
from pfia.conditions.standin import ConditionStandIn
from pfia.evaluate import review
from pfia.extraction import PrecomputedExtractor
from pfia.ledger import build_ledger
from pfia.report.outputs import (BLOCKS, CONSTRAINS, FITS, NOT_USED, StrategyError, load_strategy,
                                 mandate_fit_context, redline_context)

BASE = Path(__file__).resolve().parents[1]
REG = BASE / "data" / "registers"
FIX = BASE / "tests" / "fixtures"
STRATEGY = BASE / "data" / "mandates" / "short-term-government-credit.example.json"


def _ledger(policy="policy_deficient.txt", profile="city", facts="facts_deposit_program.json", v2=True,
            source="model-run"):
    rs = loader.load(REG)
    entity = json.loads((BASE / "data" / "profiles" / f"{profile}.json").read_text(encoding="utf-8"))
    pf = json.loads((FIX / facts).read_text(encoding="utf-8"))
    doc = (FIX / policy).read_text(encoding="utf-8")
    run = run_extraction(rs, HeuristicAdapter(), doc, entity, pf)
    # `source` stands in for a review-grade reader; "heuristic" reproduces an offline run.
    result = review(rs, entity, pf, doc, PrecomputedExtractor(run.payload, source=source))
    block = None
    if v2:
        cat = load_catalogue(REG / "instrument-conditions" / "register.json")
        r = wiring.run(cat, rs, doc, rs.expand_classes(entity["classes"]), ConditionStandIn(), REG,
                       authorized_override=pf.get("authorized_instruments"))
        block = wiring.ledger_block(cat, r)
    return build_ledger(rs, result, doc, policy, "heuristic", instrument_conditions=block)


class TestRedline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = _ledger()
        cls.ctx = redline_context(cls.ledger, REG, "City of Example")
        cls.rs = loader.load(REG)

    def test_only_core_and_instrument_items_are_amended(self):
        for a in self.ctx["amendments"] + self.ctx["optional"]:
            for cid in a["ids"]:
                if cid.startswith("TX-PFIA"):
                    self.assertEqual(self.rs.control(cid).relevance, "CORE", cid)

    def test_instrument_conflicts_name_the_condition_and_its_text(self):
        v2 = [a for a in self.ctx["amendments"] if a["source"] == "Schedule B v2"]
        self.assertTrue(any("BCD-04" in a["ids"] for a in v2))
        self.assertTrue(all(a["delete"] for a in v2))

    def test_advisory_core_is_optional_and_can_be_excluded(self):
        self.assertTrue(self.ctx["optional"])
        strict = redline_context(self.ledger, REG, "City of Example", statutory_only=True)
        self.assertEqual(strict["optional"], [])

    def test_weak_readings_are_held_not_proposed(self):
        proposed = {i for a in self.ctx["amendments"] for i in a["ids"]}
        for h in self.ctx["held"]:
            self.assertFalse(set(h["ids"]) & proposed)

    def test_entity_name_filled_and_only_decisions_counted(self):
        text = " ".join(a["proposed"] for a in self.ctx["amendments"] + self.ctx["optional"])
        self.assertNotIn("[Entity]", text)
        self.assertIn("City of Example", text)
        self.assertGreater(self.ctx["counts"]["blanks"], 0)

    def test_offline_reader_findings_are_all_held(self):
        ctx = redline_context(_ledger(source="heuristic"), REG, "City of Example")
        self.assertFalse([a for a in ctx["amendments"] if a["source"] == "Schedule A"])
        self.assertTrue(any(i.startswith("TX-PFIA") for h in ctx["held"] for i in h["ids"]))

    def test_without_v2_falls_back_to_the_0180_schedule(self):
        ctx = redline_context(_ledger(v2=False), REG, "City of Example")
        self.assertTrue(any(a["source"] == "0.18.0 schedule" for a in ctx["amendments"]))


class TestMandateFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalogue(REG / "instrument-conditions" / "register.json")
        cls.strategy = load_strategy(STRATEGY, cls.cat)

    def test_strategy_file_is_validated(self):
        bad = json.loads(STRATEGY.read_text(encoding="utf-8"))
        bad["instruments"]["COMMERCIAL_PAPER"]["terms"]["CP-99"] = 1
        path = Path(tempfile.mkdtemp()) / "s.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with self.assertRaisesRegex(StrategyError, "CP-99"):
            load_strategy(path, self.cat)

    def _synthetic(self):
        ledger = {"ledger_sha256": "ab" * 32, "document": {"source_name": "p.pdf"}, "sections": {},
                  "instrument_conditions": {"status": "proposed", "authorized": ["COMMERCIAL_PAPER", "REPO", "MMMF"],
                                            "instruments": [
            {"code": "COMMERCIAL_PAPER", "label": "Commercial paper", "status": "ALIGNED", "contradicted": [],
             "conditions": [
                {"id": "CP-01", "cite": "2256.013(1)", "component": "MATURITY", "state": "STRICTER",
                 "binding": {"limit": 180.0, "unit": "days", "strict": False}, "statutory_value": {"limit": 365, "unit": "days", "strict": False}},
                {"id": "CP-02", "cite": "2256.013(2)", "component": "CREDIT_RATING", "state": "CONFORMING",
                 "binding": {"floor": "A-1", "scale": "SHORT_TERM", "granularity": "NOTCH", "min_agencies": 1, "basis": "AT_PURCHASE"},
                 "statutory_value": {"floor": "A-1", "scale": "SHORT_TERM"}},
                {"id": "CP-03", "cite": "2256.013(2)(A)-(B)", "component": "CREDIT_RATING", "state": "SILENT",
                 "binding": ["TWO_AGENCIES", "ONE_AGENCY_PLUS_LOC"], "statutory_value": ["TWO_AGENCIES", "ONE_AGENCY_PLUS_LOC"]}]},
            {"code": "REPO", "label": "Repurchase agreements", "status": "CONFLICTS", "contradicted": ["REP-07"],
             "conditions": [{"id": "REP-04", "cite": "2256.011(b)(2)", "component": "COLLATERAL", "state": "SILENT",
                             "binding": {"limit": 100, "unit": "pct_of_principal"}, "statutory_value": {"limit": 100, "unit": "pct_of_principal"}}]},
            {"code": "MMMF", "label": "Money market funds", "status": "ALIGNED", "contradicted": [], "conditions": []}]}}
        return ledger

    def test_fit_constrains_blocks_and_not_used(self):
        ctx = mandate_fit_context(self._synthetic(), self.strategy, REG, "X")
        fit = {r["code"]: r["fit"] for r in ctx["rows"]}
        self.assertEqual(fit["COMMERCIAL_PAPER"], CONSTRAINS)      # policy caps at 180 days; strategy 270
        self.assertEqual(fit["REPO"], FITS)                       # 102% meets the 100% floor
        self.assertEqual(fit["BROKERED_CD"], BLOCKS)              # not authorized
        self.assertEqual(fit["MMMF"], FITS)
        self.assertTrue(any("Fit is not compliance" in n and "REP-07" in n for n in ctx["notes"]))

    def test_unreadable_policy_term_is_not_a_fit(self):
        ledger = self._synthetic()
        ledger["instrument_conditions"]["instruments"][0]["conditions"][0]["state"] = "UNKNOWN"
        ctx = mandate_fit_context(ledger, self.strategy, REG, "X")
        cp = next(r for r in ctx["rows"] if r["code"] == "COMMERCIAL_PAPER")
        self.assertEqual(cp["fit"], "Cannot determine")
        self.assertFalse(ctx["can_run_as_designed"])

    def test_portfolio_limits_are_reviewer_entered(self):
        limits = {"max_stated_maturity": {"value": 2, "unit": "years"}}
        ctx = mandate_fit_context(self._synthetic(), self.strategy, REG, "X", limits)
        row = next(p for p in ctx["portfolio"] if p["key"] == "max_stated_maturity")
        self.assertEqual(row["fit"], CONSTRAINS)
        wam = next(p for p in ctx["portfolio"] if p["key"] == "max_wam_pooled")
        self.assertEqual(wam["policy"], "Not extracted")

    def test_policy_only_instruments_are_listed_not_used(self):
        ledger = self._synthetic()
        ledger["instrument_conditions"]["authorized"].append("BANKERS_ACCEPTANCE")
        ctx = mandate_fit_context(ledger, self.strategy, REG, "X")
        self.assertIn(("BANKERS_ACCEPTANCE", NOT_USED), [(r["code"], r["fit"]) for r in ctx["rows"]])


@unittest.skipUnless(__import__("importlib").util.find_spec("jinja2"), "jinja2 not installed")
class TestRendering(unittest.TestCase):
    def test_cli_renders_both_html_outputs(self):
        ledger = _ledger()
        tmp = Path(tempfile.mkdtemp())
        (tmp / "l.json").write_text(json.dumps(ledger), encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(BASE / "src")}
        for cmd, out in ((["redline"], "r.html"),
                         (["mandate-fit", "--strategy", str(STRATEGY)], "m.html")):
            r = subprocess.run([sys.executable, "-m", "pfia", *cmd, "--ledger", str(tmp / "l.json"),
                                "--entity", "City of Example", "--html", str(tmp / out)],
                               cwd=BASE, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            html = (tmp / out).read_text(encoding="utf-8")
            self.assertIn("City of Example", html)
        self.assertIn("Draft resolution", (tmp / "r.html").read_text(encoding="utf-8"))
        m = (tmp / "m.html").read_text(encoding="utf-8")
        self.assertIn("Authorized Investment Review", m)
        self.assertIn("Investment Policy Summary", m)
        self.assertNotIn("synthetic policy, offline reader", m)
        self.assertLess(m.index("Investment Policy Summary"), m.index("Portfolio-level parameters"))
        self.assertLess(m.index("Portfolio-level parameters"), m.index("Authorized Investment Review"))
