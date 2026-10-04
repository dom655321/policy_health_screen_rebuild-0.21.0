"""Schedule B v2 condition catalogue and deterministic evaluator."""
import json
import tempfile
import unittest
from pathlib import Path

from pfia.conditions import (
    BY_REFERENCE, CONFORMING, CONTRADICTED, SILENT, STRICTER, UNKNOWN,
    CatalogueError, evaluate_condition, evaluate_instrument, load_catalogue,
)
from pfia.conditions import scales
from pfia.conditions.evaluate import NOT_APPLICABLE, UNRESOLVED

BASE = Path(__file__).resolve().parents[1]
CAT_PATH = BASE / "data" / "registers" / "instrument-conditions" / "register.json"


class TestCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalogue(CAT_PATH)  # raises if any quote is not in the snapshot
        cls.idx = {c.id: c for c in cls.cat.conditions}

    def test_counts_and_status(self):
        self.assertEqual(self.cat.meta["status"], "proposed")
        self.assertEqual(len(self.cat.instruments), 29)
        # Approved re-review TR-2026-10-02: 80 active, 49 retired.
        self.assertEqual(len(self.cat.conditions), 80)
        self.assertEqual(sum(len(i.retired) for i in self.cat.instruments.values()), 49)

    def test_israel_bonds_present(self):
        self.assertIn("ISRAEL_BONDS", self.cat.instruments)

    def test_no_reciprocal_deposit_condition(self):
        # Verified absent from current Sec. 2256.010(b); the 2017 checklist is superseded.
        text = json.dumps([c.requirement for c in self.cat.instruments["BROKERED_CD"].conditions]).lower()
        self.assertNotIn("reciprocal", text)
        self.assertNotIn("customers of other", text)

    def test_pool_rating_tested_once(self):
        rating = [c for c in self.cat.instruments["INVESTMENT_POOL"].conditions if c.component == "CREDIT_RATING"]
        self.assertEqual([c.id for c in rating], ["POL-10"])

    def test_negotiable_cd_is_one_disjunctive_condition(self):
        conds = self.cat.instruments["NEGOTIABLE_CD"].conditions
        self.assertEqual(len(conds), 1)
        self.assertEqual(conds[0].mode, "ANY_OF")

    def test_reverse_repo_inherits_repo(self):
        ids = [c.id for c in self.cat.conditions_for("REVERSE_REPO")]
        self.assertEqual(ids[:2], ["RRP-01", "RRP-02"])
        self.assertIn("REP-04", ids)
        self.assertIn("REP-11", ids)               # kept in the approved re-review
        self.assertEqual(len(ids), 2 + len(self.cat.instruments["REPO"].conditions))

    def test_manager_duties_flagged(self):
        duties = [c.id for c in self.cat.conditions if c.binds == "INVESTMENT_MANAGER"]
        self.assertEqual(set(duties), {"REP-09", "REP-10", "REP-11"})   # ICB-13/14 dropped with the instrument

    def _mutated(self, fn):
        doc = json.loads(CAT_PATH.read_text(encoding="utf-8"))
        fn(doc)
        tmp = Path(tempfile.mkdtemp()) / "register.json"
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        return tmp

    def test_quote_not_in_statute_fails(self):
        def tamper(doc):
            doc["instruments"][0]["conditions"][0]["quote"] = "obligations of any federal agency of any structure"
        path = self._mutated(tamper)
        with self.assertRaisesRegex(CatalogueError, "USO-01: quote not found"):
            load_catalogue(path, snapshot=BASE / "data" / "sources" / "GV.2256.txt")

    def test_unknown_mode_fails(self):
        def tamper(doc):
            doc["instruments"][0]["conditions"][0]["test"]["mode"] = "VIBES"
        path = self._mutated(tamper)
        with self.assertRaisesRegex(CatalogueError, "unknown test mode"):
            load_catalogue(path, verify_quotes=False)


class TestScales(unittest.TestCase):
    def test_cross_agency_equivalents(self):
        self.assertEqual(scales.compare("P-1", "A-1", "SHORT_TERM"), 0)
        self.assertEqual(scales.compare("F1+", "A-1", "SHORT_TERM"), -1)
        self.assertEqual(scales.compare("Aa3", "AA-", "LONG_TERM"), 0)

    def test_notch_reading_of_a(self):
        self.assertEqual(scales.compare("A-", "A", "LONG_TERM"), 1)
        self.assertEqual(scales.compare("A+", "A", "LONG_TERM"), -1)

    def test_category_reading_disregards_gradations(self):
        self.assertEqual(scales.compare("AA-", "AA", "LONG_TERM", "CATEGORY"), 0)
        self.assertEqual(scales.compare("AA+", "AA", "LONG_TERM", "CATEGORY"), -1)
        self.assertEqual(scales.compare("A+", "AA", "LONG_TERM", "CATEGORY"), 1)

    def test_unknown_rating_raises(self):
        with self.assertRaises(scales.UnknownRating):
            scales.rank("investment grade", "LONG_TERM")


class TestConditionModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cat = load_catalogue(CAT_PATH)
        cls.c = {c.id: c for c in cat.conditions}

    def ev(self, cid, fact, activation=None):
        return evaluate_condition(self.c[cid], fact, activation)

    # CAP
    def test_cap_stricter_equal_looser(self):
        self.assertEqual(self.ev("CP-01", {"stated": True, "value": 270, "unit": "days"}).state, STRICTER)
        self.assertEqual(self.ev("CP-01", {"stated": True, "value": 365, "unit": "days"}).state, CONFORMING)
        self.assertEqual(self.ev("CP-01", {"stated": True, "value": 397, "unit": "days"}).state, CONTRADICTED)

    def test_strict_statutory_bound(self):
        # Sec. 2256.014(b)(2): "less than two years". "Two years or less" admits exactly two.
        self.assertEqual(self.ev("MF-03", {"stated": True, "value": 2, "unit": "years", "inclusive": True}).state, CONTRADICTED)
        self.assertEqual(self.ev("MF-03", {"stated": True, "value": 2, "unit": "years", "inclusive": False}).state, CONFORMING)

    def test_exact_unit_conversion(self):
        self.assertEqual(self.ev("CMO-03", {"stated": True, "value": 60, "unit": "months"}).state, STRICTER)
        self.assertEqual(self.ev("CMO-03", {"stated": True, "value": 120, "unit": "months"}).state, CONFORMING)

    def test_approximate_conversion_near_limit_is_unknown(self):
        r = self.ev("CMO-03", {"stated": True, "value": 3652, "unit": "days"})
        self.assertEqual(r.state, UNKNOWN)
        self.assertEqual(self.ev("CMO-03", {"stated": True, "value": 1825, "unit": "days"}).state, STRICTER)

    # FLOOR
    def test_floor(self):
        self.assertEqual(self.ev("SLN-01", {"stated": True, "value": 102, "unit": "pct_of_loan_value"}).state, STRICTER)
        self.assertEqual(self.ev("SLN-01", {"stated": True, "value": 98, "unit": "pct_of_loan_value"}).state, CONTRADICTED)

    # RATING_FLOOR
    def test_muni_rating(self):
        self.assertEqual(self.ev("MUN-02", {"stated": True, "value": "A-"}).state, CONTRADICTED)
        self.assertEqual(self.ev("MUN-02", {"stated": True, "value": "AA"}).state, STRICTER)
        self.assertEqual(self.ev("MUN-02", {"stated": True, "value": "A"}).state, CONFORMING)

    def test_category_reading_on_a_retired_condition(self):
        # IHB-02 is retired with its instrument; the category reading still evaluates.
        cat = load_catalogue(CAT_PATH)
        ihb = next(c for c in cat.instruments["IHE_CORPORATE_BOND"].retired if c.id == "IHB-02")
        self.assertEqual(evaluate_condition(ihb, {"stated": True, "value": "AA-"}).state, CONFORMING)

    def test_pool_rating_basis(self):
        r = self.ev("POL-10", {"stated": True, "value": "AAAm", "basis": "AT_PURCHASE"})
        self.assertEqual(r.state, CONTRADICTED)
        self.assertEqual(self.ev("POL-10", {"stated": True, "value": "AAA-mmf", "basis": "CONTINUOUS"}).state, CONFORMING)

    def test_unparseable_rating_is_unknown(self):
        self.assertEqual(self.ev("MUN-02", {"stated": True, "value": "investment grade"}).state, UNKNOWN)

    # SUBSET
    def test_subset(self):
        self.assertEqual(self.ev("SLN-04", {"stated": True, "value": ["CASH", "PLEDGED_IRREVOCABLE_LOC"]}).state, STRICTER)
        r = self.ev("SLN-04", {"stated": True, "value": ["CASH", "OTHER:any authorized investment"]})
        self.assertEqual(r.state, CONTRADICTED)
        self.assertEqual(self.ev("SLN-04", {"stated": True, "value": ["CASH", "TREASURIES"]}).state, UNKNOWN)

    # ANY_OF
    def test_commercial_paper_single_agency_without_loc(self):
        self.assertEqual(self.ev("CP-03", {"stated": True, "outside": True}).state, CONTRADICTED)
        self.assertEqual(self.ev("CP-03", {"stated": True, "value": ["TWO_AGENCIES"]}).state, STRICTER)

    def test_negotiable_cd_single_path_is_stricter_not_half(self):
        self.assertEqual(self.ev("NCD-01", {"stated": True, "value": ["BANK_CD_RATING_1"]}).state, STRICTER)

    # REQUIRED / PROHIBITED / silence / reference
    def test_required(self):
        self.assertEqual(self.ev("BRD-04", {"stated": True}).state, CONFORMING)
        self.assertEqual(self.ev("BRD-04", {"stated": True, "contradicted": True}).state, CONTRADICTED)
        self.assertEqual(self.ev("BRD-04", {"stated": False}).state, SILENT)
        self.assertEqual(self.ev("BRD-04", {"stated": False, "by_reference": True}).state, BY_REFERENCE)

    def test_prohibited(self):
        self.assertEqual(self.ev("PRH-01", {"authorized": True}).state, CONTRADICTED)
        self.assertEqual(self.ev("PRH-01", {"excluded": True}).state, CONFORMING)
        self.assertEqual(self.ev("PRH-01", {}).state, SILENT)

    def test_missing_fact_is_unknown_not_silent(self):
        self.assertEqual(self.ev("CP-01", None).state, UNKNOWN)

    # activation
    def test_activation(self):
        self.assertEqual(self.ev("REP-09", {"stated": False}, {"joint_account_via_manager_authorized": False}).state, NOT_APPLICABLE)
        self.assertEqual(self.ev("REP-09", {"stated": False}, {}).state, UNRESOLVED)
        self.assertEqual(self.ev("REP-09", {"stated": True}, {}).state, CONFORMING)


class TestInstrumentRollup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalogue(CAT_PATH)

    def test_deficient_commercial_paper_names_the_condition(self):
        # tests/fixtures/policy_deficient.txt: "270 days or fewer, rated by at least one
        # nationally recognized credit rating agency" - no floor stated, no letter of credit.
        facts = {"CP-01": {"stated": True, "value": 270, "unit": "days"},
                 "CP-02": {"stated": False},
                 "CP-03": {"stated": True, "outside": True}}
        r = evaluate_instrument(self.cat, "COMMERCIAL_PAPER", facts)
        self.assertEqual(r.status, "CONFLICTS")
        self.assertEqual(r.contradicted, ["CP-03"])
        self.assertEqual(r.not_restated, ["CP-02"])

    def test_unknown_blocks_aligned(self):
        facts = {"CP-01": {"stated": True, "value": 270, "unit": "days"},
                 "CP-02": {"stated": True, "value": "A-1"},
                 "CP-03": None}
        self.assertEqual(evaluate_instrument(self.cat, "COMMERCIAL_PAPER", facts).status, "REVIEW_REQUIRED")

    def test_silence_never_changes_the_status(self):
        facts = {c.id: {"stated": False} for c in self.cat.conditions_for("COMMERCIAL_PAPER")}
        r = evaluate_instrument(self.cat, "COMMERCIAL_PAPER", facts)
        self.assertEqual(r.status, "ALIGNED")
        self.assertEqual(len(r.not_restated), 3)

    def test_inactive_conditions_are_left_out(self):
        facts = {f"REP-0{i}": {"stated": True} for i in (1, 2, 5, 6, 7)}
        facts.update({"REP-03": {"stated": True, "value": ["CASH", "OBLIGATIONS_2256_009A1"]},
                      "REP-04": {"stated": True, "value": 102, "unit": "pct_of_principal"},
                      "REP-08": {"stated": True, "value": ["PRIMARY_DEALER_FRB"]}})
        r = evaluate_instrument(self.cat, "REPO", facts, {"joint_account_via_manager_authorized": False})
        self.assertEqual(r.status, "ALIGNED")
        self.assertEqual(r.not_restated, [])


class TestTeamReview(unittest.TestCase):
    """Approved re-review TR-2026-10-02."""
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalogue(CAT_PATH)

    def test_fully_dropped_instrument_is_not_reviewed_never_aligned(self):
        r = evaluate_instrument(self.cat, "MUNICIPAL_UTILITY_HEDGE", {})
        self.assertEqual(r.status, "NOT_REVIEWED")

    def test_retired_conditions_are_kept_for_the_trail(self):
        sln = self.cat.instruments["SECURITIES_LENDING"]
        self.assertEqual({c.id for c in sln.retired}, {"SLN-02", "SLN-10"})
        self.assertEqual(self.cat.instruments["REPO"].retired, ())

    def test_approved_verdicts(self):
        ids = {c.id for c in self.cat.conditions}
        self.assertTrue({"GTD-01", "MF-01", "CMO-02", "DCD-03", "DCD-04", "DCD-05", "REP-11", "GIC-08",
                         "POL-01", "POL-05", "POL-06", "POL-07", "POL-11"} <= ids)
        self.assertFalse({"SLN-02", "SLN-10", "BRD-01", "BCD-05", "POL-03"} & ids)
        for code in ("ISD_CORPORATE_BOND", "IHE_CASH_MGMT_FUND", "IHE_CORPORATE_BOND"):
            self.assertTrue(self.cat.instruments[code].not_reviewed, code)
        sln06 = next(c for c in self.cat.conditions if c.id == "SLN-06")
        self.assertIn("Section 2256.009, .013, .014 or .016", sln06.requirement)

    def test_custody_is_congruent_across_repo_and_securities_lending(self):
        def custody(code):
            return {c.test["fact"]: c for c in self.cat.instruments[code].conditions
                    if c.component == "CUSTODY"}
        repo, sln = custody("REPO"), custody("SECURITIES_LENDING")
        expected = {"pledged_to_entity", "held_in_entity_name", "deposited_with_entity_or_approved_third_party"}
        self.assertEqual(set(repo), expected)
        self.assertEqual(set(sln), expected)
        for key in expected:
            a, b = repo[key], sln[key]
            self.assertEqual((a.mode, a.binds), (b.mode, b.binds), key)
            self.assertEqual(a.test.get("contradiction_cues"), b.test.get("contradiction_cues"), key)


class TestStepZeroFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = {c.id: c for c in load_catalogue(CAT_PATH).conditions}

    def test_percentage_base_must_match(self):
        # 15 percent of the portfolio is not 15 percent of monthly average fund balance.
        r = evaluate_condition(self.c["MF-05"], {"stated": True, "value": 15, "unit": "pct"})
        self.assertEqual(r.state, UNKNOWN)
        r = evaluate_condition(self.c["MF-05"], {"stated": True, "value": 15, "unit": "pct_of_portfolio"})
        self.assertEqual(r.state, UNKNOWN)
        r = evaluate_condition(self.c["MF-05"], {"stated": True, "value": 10, "unit": "pct_of_monthly_avg_balance"})
        self.assertEqual(r.state, STRICTER)

    def test_quote_must_sit_in_a_cited_section(self):
        doc = json.loads(CAT_PATH.read_text(encoding="utf-8"))
        # A real Sec. 2256.013 phrase attributed to Sec. 2256.012 must fail.
        doc["instruments"][0]["conditions"][0]["cite"] = "2256.012(1)"
        doc["instruments"][0]["conditions"][0]["quote"] = "has a stated maturity of 365 days or fewer from the date of its issuance"
        tmp = Path(tempfile.mkdtemp()) / "register.json"
        tmp.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(CatalogueError, "not found verbatim in cited section"):
            load_catalogue(tmp, snapshot=BASE / "data" / "sources" / "GV.2256.txt")

    def test_statute_snapshot_reproduces(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("fetch_statute", BASE / "scripts" / "fetch_statute.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        manifest = json.loads((BASE / "data" / "sources" / "MANIFEST.json").read_text(encoding="utf-8"))
        raw = (BASE / manifest["raw_path"]).read_bytes()
        self.assertEqual(mod.sha256(raw), manifest["raw_sha256"])
        text = mod.normalize(mod._decode(raw))
        self.assertEqual(mod.sha256(text.encode("utf-8")), manifest["text_sha256"])
        self.assertEqual(text, (BASE / "data" / "sources" / "GV.2256.txt").read_text(encoding="utf-8"))
