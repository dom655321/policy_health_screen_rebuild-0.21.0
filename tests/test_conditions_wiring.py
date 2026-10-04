"""Schedule B v2 wiring: detection mapping, verified facts, stand-in run, ledger block."""
import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.adapter.providers.replay import ReplayAdapter
from pfia.conditions import load_catalogue, wiring
from pfia.conditions.standin import ConditionStandIn
from pfia.instruments import detect

BASE = Path(__file__).resolve().parents[1]
REG = BASE / "data" / "registers"
FIX = BASE / "tests" / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


class TestWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REG)
        cls.cat = load_catalogue(REG / "instrument-conditions" / "register.json")
        cls.sup = wiring.load_supplement(REG)
        cls.city = cls.rs.expand_classes(["MUNICIPALITY"])

    def _run(self, doc, classes=None, adapter=None, override=None):
        return wiring.run(self.cat, self.rs, doc, classes or self.city, adapter or ConditionStandIn(), REG,
                          authorized_override=override)

    def test_deficient_deposits_conflicts_are_named(self):
        facts = json.loads(_read("facts_deposit_program.json"))
        run = self._run(_read("policy_deficient.txt"), override=facts["authorized_instruments"])
        by = {r.code: r for r in run.results}
        self.assertEqual(by["BROKERED_CD"].status, "CONFLICTS")
        self.assertEqual(set(by["BROKERED_CD"].contradicted), {"BCD-04"})   # BCD-05 not testable (TR-2026-10-02)
        self.assertIn("MUN-02", by["MUNI_OBLIGATIONS"].contradicted)
        self.assertEqual(wiring.section_status(run), "REVISIONS_RECOMMENDED")

    def test_single_agency_commercial_paper_is_a_conflict(self):
        run = self._run(_read("policy_conforming.txt"), self.rs.expand_classes(["WATER_AUTHORITY"])
                        if "WATER_AUTHORITY" in self.rs.entity_classes else self.city)
        cp = next(r for r in run.results if r.code == "COMMERCIAL_PAPER")
        self.assertEqual(cp.contradicted, ["CP-03"])

    def test_unquoted_affirmative_claims_are_discarded(self):
        raw = {"conditions": {"CP-01": {"stated": True, "value": 90, "unit": "days", "quote": "not in the text"},
                              "CP-02": {"stated": False}},
               "activation": {"broker_path_authorized": {"value": True, "quote": "nowhere"}}}
        facts, activation, discarded = wiring.verify_facts(raw, "Commercial paper is authorized.", "COMMERCIAL_PAPER")
        self.assertNotIn("CP-01", facts)          # becomes UNKNOWN, never trusted
        self.assertEqual(facts["CP-02"], {"stated": False})
        self.assertEqual(activation, {})
        self.assertEqual(len(discarded), 2)

    def test_missing_answers_are_unknown_not_silent(self):
        run = self._run(_read("policy_conforming.txt"), adapter=ReplayAdapter({}))
        for r in run.results:
            if r.code != "CMO_IO_PO_INVERSE":
                self.assertEqual(r.status, "REVIEW_REQUIRED", r.code)

    def test_code_mapping(self):
        codes = wiring.v2_codes(["DECOMMISSIONING_TRUST_INVESTMENT", "MINERAL_RIGHTS_TRUST_INVESTMENT",
                                 "IHE_CORPORATE_BOND", "COMMERCIAL_PAPER"], self.cat, self.sup, self.city)
        self.assertIn("MINERAL_RIGHTS_MUNI", codes)
        self.assertNotIn("MINERAL_RIGHTS_JUCO", codes)
        self.assertNotIn("IHE_CORPORATE_BOND", codes)      # class-gated
        self.assertIn("COMMERCIAL_PAPER", codes)

    def test_base_detection_is_untouched(self):
        doc = "Authorized investments: (a) obligations of this state; (b) bonds of the State of Israel."
        base = detect(self.rs, doc, REG)
        merged = detect(self.rs, doc, REG, lexicon=wiring.merged_lexicon(REG))
        self.assertNotIn("TX_OBLIGATIONS", base.authorized)
        self.assertNotIn("ISRAEL_BONDS", base.authorized)
        self.assertIn("ISRAEL_BONDS", merged.authorized)

    def test_prompt_carries_the_request_and_no_verdict_vocabulary(self):
        conds = self.cat.conditions_for("COMMERCIAL_PAPER")
        prompt = wiring.build_prompt("COMMERCIAL_PAPER", "Commercial paper", conds, [(0, "text")])
        request = json.loads(prompt.split("<request>", 1)[1].split("</request>", 1)[0])
        self.assertEqual([c["id"] for c in request["conditions"]], ["CP-01", "CP-02", "CP-03"])
        for word in ("CONFORMING", "CONTRADICTED", "DEFICIENT", "STRICTER"):
            self.assertNotIn(word, prompt)

    def test_ledger_block_is_proposed_and_complete(self):
        run = self._run(_read("policy_deficient.txt"))
        block = wiring.ledger_block(self.cat, run)
        self.assertEqual(block["status"], "proposed")
        self.assertIn("section_status_if_adopted", block)
        for inst in block["instruments"]:
            for c in inst["conditions"]:
                self.assertIn("cite", c)
                self.assertIn("state", c)


if __name__ == "__main__":
    unittest.main()
