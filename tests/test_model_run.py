"""Live-provider plumbing (with a substituted transport), cassettes, two readers, bake-off scoring."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pfia import loader
from pfia.adapter.base import AdapterError
from pfia.adapter.providers import AnthropicAdapter, GeminiAdapter
from pfia.adapter.providers.replay import RecordingAdapter, ReplayAdapter
from pfia.conditions import load_catalogue, wiring
from pfia.conditions.standin import ConditionStandIn

BASE = Path(__file__).resolve().parents[1]
REG = BASE / "data" / "registers"
SCHEMA = wiring.response_schema()
FACTS = {"conditions": {"CP-01": {"stated": True, "value": 270, "unit": "days", "quote": "270 days"}},
         "activation": {}}


def _anthropic(payload):
    with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        a = AnthropicAdapter("claude-sonnet-5-5")
    a._post = lambda url, body, headers: payload
    return a


class TestProviders(unittest.TestCase):
    def test_anthropic_conditions_contract_and_provenance(self):
        a = _anthropic({"model": "claude-sonnet-5-5-20260915", "stop_reason": "end_turn",
                        "usage": {"input_tokens": 4000, "output_tokens": 600},
                        "content": [{"type": "text", "text": "```json\n" + json.dumps(FACTS) + "\n```"}]})
        out = a.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)
        self.assertEqual(out["conditions"]["CP-01"]["value"], 270)
        self.assertEqual(a.last_meta["served_model"], "claude-sonnet-5-5-20260915")
        self.assertEqual(a.last_meta["input_tokens"], 4000)

    def test_gemini_conditions_contract_and_provenance(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            g = GeminiAdapter("gemini-3.8-flash")
        g._post = lambda url, body, headers: {
            "modelVersion": "gemini-3.8-flash-001",
            "usageMetadata": {"promptTokenCount": 3900, "candidatesTokenCount": 500, "thoughtsTokenCount": 200},
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(FACTS)}]}}]}
        out = g.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)
        self.assertIn("CP-01", out["conditions"])
        self.assertEqual(g.last_meta["output_tokens"], 700)

    def test_unusable_conditions_payload_is_an_adapter_error(self):
        a = _anthropic({"content": [{"type": "text", "text": '{"elements": []}'}]})
        with self.assertRaises(AdapterError):
            a.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)

    def test_truncated_conditions_response_is_refused(self):
        a = _anthropic({"stop_reason": "max_tokens", "content": [{"type": "text", "text": json.dumps(FACTS)}]})
        with self.assertRaisesRegex(AdapterError, "ceiling"):
            a.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)

    def test_extra_body_comes_from_the_environment(self):
        seen = {}
        a = _anthropic({"content": [{"type": "text", "text": json.dumps(FACTS)}]})
        a._post = lambda url, body, headers: seen.update(body) or {"content": [{"type": "text", "text": json.dumps(FACTS)}]}
        with mock.patch.dict(os.environ, {"PFIA_ANTHROPIC_EXTRA_BODY": '{"metadata": {"user_id": "bakeoff"}}'}):
            a.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)
        self.assertEqual(seen["metadata"], {"user_id": "bakeoff"})
        self.assertEqual(seen["model"], "claude-sonnet-5-5")

    def test_cassette_records_provenance_and_never_the_key(self):
        a = _anthropic({"model": "claude-sonnet-5-5-20260915",
                        "content": [{"type": "text", "text": json.dumps(FACTS)}]})
        path = Path(tempfile.mkdtemp()) / "cassette.json"
        rec = RecordingAdapter(a, path)
        rec.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)
        rec.save(case="t")
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("test-key", text)
        doc = json.loads(text)
        self.assertEqual(doc["_run"]["served_models"], ["claude-sonnet-5-5-20260915"])
        self.assertIn("prompt_sha256", doc["_meta"]["B2:COMMERCIAL_PAPER"])
        self.assertEqual(ReplayAdapter(path).provenance["case"], "t")


class TestGeminiThreeX(unittest.TestCase):
    def _g(self, model="gemini-3.8-flash", env=None):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", **(env or {})}):
            return GeminiAdapter(model)

    def test_no_temperature_and_thinking_level_from_env(self):
        g = self._g()
        with mock.patch.dict(os.environ, {"PFIA_GEMINI_THINKING_LEVEL": "low"}):
            cfg = g._body("p")["generationConfig"]
        self.assertNotIn("temperature", cfg)
        self.assertEqual(cfg["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertEqual(cfg["responseMimeType"], "application/json")
        self.assertGreaterEqual(cfg["maxOutputTokens"], 32768)

    def test_older_models_keep_temperature_zero(self):
        self.assertEqual(self._g("gemini-2.5-pro")._body("p")["generationConfig"]["temperature"], 0)

    def test_extra_body_merges_without_dropping_defaults(self):
        seen = {}
        g = self._g()
        g._post = lambda url, body, headers: seen.update(body) or {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(FACTS)}]}}]}
        with mock.patch.dict(os.environ, {"PFIA_GEMINI_EXTRA_BODY": '{"generationConfig": {"thinkingConfig": {"thinkingLevel": "high"}}}'}):
            g.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)
        self.assertEqual(seen["generationConfig"]["thinkingConfig"], {"thinkingLevel": "high"})
        self.assertEqual(seen["generationConfig"]["responseMimeType"], "application/json")

    def test_thought_parts_are_never_parsed(self):
        g = self._g()
        g._post = lambda url, body, headers: {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "reasoning about CP-01...", "thought": True}, {"text": json.dumps(FACTS)}]}}]}
        self.assertIn("CP-01", g.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)["conditions"])

    def test_blocked_prompt_is_an_adapter_error(self):
        g = self._g()
        g._post = lambda url, body, headers: {"promptFeedback": {"blockReason": "SAFETY"}}
        with self.assertRaisesRegex(AdapterError, "blocked"):
            g.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)

    def test_rate_limit_is_retried_then_succeeds(self):
        import io
        import urllib.error
        g = self._g()
        calls = {"n": 0}

        def post(url, body, headers):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError(url, 429, "Too Many Requests", {"retry-after": "0"}, io.BytesIO(b"{}"))
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(FACTS)}]}}]}
        g._post, g._sleep = post, lambda s: None
        self.assertIn("CP-01", g.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)["conditions"])
        self.assertEqual(calls["n"], 3)

    def test_http_error_carries_the_provider_message(self):
        import io
        import urllib.error
        a = _anthropic({})
        body = b'{"type":"error","error":{"type":"not_found_error","message":"model: claude-x not found"}}'
        a._post = lambda url, b, h: (_ for _ in ()).throw(urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(body)))
        with self.assertRaisesRegex(AdapterError, "not_found_error: model: claude-x not found"):
            a.ask("prompt", "B2:COMMERCIAL_PAPER", SCHEMA)


class TestCliStarts(unittest.TestCase):
    def test_review_honours_pfia_adapter_and_model(self):
        import subprocess
        env = {**os.environ, "PYTHONPATH": str(BASE / "src"), "PFIA_ADAPTER": "heuristic"}
        for cmd in (["review", "--help"], ["extract", "--help"], ["adapter-check", "--help"]):
            r = subprocess.run([sys.executable, "-m", "pfia", *cmd], cwd=BASE, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-400:])
        env.update({"PFIA_ADAPTER": "gemini", "PFIA_MODEL": "", "GEMINI_API_KEY": "x"})
        r = subprocess.run([sys.executable, "-m", "pfia", "review", "--profile", "data/profiles/city.json",
                            "--policy", "tests/fixtures/policy_deficient.txt", "--schedule-b-v2"],
                           cwd=BASE, env=env, capture_output=True, text=True)
        self.assertIn("requires --model or PFIA_MODEL", r.stdout + r.stderr)


class TestLedgerWrite(unittest.TestCase):
    def test_out_path_directory_is_created(self):
        from pfia.ledger import write_ledger
        target = Path(tempfile.mkdtemp()) / "new" / "dir" / "ledger.json"
        write_ledger(str(target), {"ok": True})
        self.assertTrue(target.exists())


class TestBakeoffKeys(unittest.TestCase):
    def test_candidates_without_keys_are_skipped(self):
        sys.path.insert(0, str(BASE / "scripts"))
        import bakeoff
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "x"}, clear=True):
            self.assertEqual(bakeoff.missing_keys({"provider": "anthropic"}), ["ANTHROPIC_API_KEY"])
            self.assertEqual(bakeoff.missing_keys({"provider": "gemini"}), [])
            self.assertEqual(bakeoff.missing_keys({"provider": "anthropic", "second": {"provider": "gemini"}}),
                             ["ANTHROPIC_API_KEY"])

    def test_candidate_env_is_restored(self):
        sys.path.insert(0, str(BASE / "scripts"))
        import bakeoff
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PFIA_GEMINI_THINKING_LEVEL", None)
            with bakeoff.candidate_env({"env": {"PFIA_GEMINI_THINKING_LEVEL": "low"}}):
                self.assertEqual(os.environ["PFIA_GEMINI_THINKING_LEVEL"], "low")
            self.assertNotIn("PFIA_GEMINI_THINKING_LEVEL", os.environ)


class _Contrarian(ConditionStandIn):
    """Agrees with the stand-in except it reads every stated figure one unit higher."""
    name = "contrarian"

    def ask(self, prompt, key, schema):
        out = super().ask(prompt, key, schema)
        for fact in out["conditions"].values():
            if isinstance(fact.get("value"), (int, float)):
                fact["value"] += 1
        return out


class TestTwoReaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REG)
        cls.cat = load_catalogue(REG / "instrument-conditions" / "register.json")
        cls.doc = (BASE / "tests" / "fixtures" / "policy_conforming.txt").read_text(encoding="utf-8")
        cls.classes = cls.rs.expand_classes(["MUNICIPALITY"])

    def test_agreement_passes_disagreement_is_unknown(self):
        conds = self.cat.conditions_for("COMMERCIAL_PAPER")
        a = ({"CP-01": {"stated": True, "value": 270, "unit": "days"}, "CP-02": {"stated": False}}, {})
        b = ({"CP-01": {"stated": True, "value": 180, "unit": "days"}, "CP-02": {"stated": False}}, {})
        facts, _, notes = wiring.reconcile(conds, a, b, "COMMERCIAL_PAPER")
        self.assertNotIn("CP-01", facts)
        self.assertEqual(facts["CP-02"], {"stated": False})
        self.assertEqual([n["condition"] for n in notes], ["CP-01"])

    def test_one_silent_reader_is_not_corroboration(self):
        conds = self.cat.conditions_for("COMMERCIAL_PAPER")
        facts, _, notes = wiring.reconcile(conds, ({"CP-03": {"stated": True, "outside": True}}, {}), ({}, {}),
                                           "COMMERCIAL_PAPER")
        self.assertNotIn("CP-03", facts)
        self.assertEqual(len(notes), 1)

    def test_disagreement_never_becomes_a_conflict(self):
        solo = wiring.run(self.cat, self.rs, self.doc, self.classes, ConditionStandIn(), REG)
        pair = wiring.run(self.cat, self.rs, self.doc, self.classes, ConditionStandIn(), REG,
                          second_adapter=_Contrarian())
        self.assertGreater(pair.disagreements, 0)
        solo_conflicts = {c for r in solo.results for c in r.contradicted}
        pair_conflicts = {c for r in pair.results for c in r.contradicted}
        self.assertTrue(pair_conflicts <= solo_conflicts)
        self.assertEqual(pair.second_adapter, "contrarian")


class TestBakeoffScoring(unittest.TestCase):
    def test_score_counts_each_error_type(self):
        sys.path.insert(0, str(BASE / "scripts"))
        import bakeoff
        run = {"v2": {"COMMERCIAL_PAPER": {"contradicted": ["CP-01"], "unknown": ["CP-03"], "active": 3},
                      "REPO": {"contradicted": [], "unknown": [], "active": 8}},
               "a_status": {"X": "CONFLICTS", "Y": "ALIGNED"}}
        truth = {"instruments": {"COMMERCIAL_PAPER": {"conflicts": ["CP-03"]}, "REPO": {"conflicts": ["REP-07"]}},
                 "controls": {"X": "ALIGNED", "Y": "CONFLICTS"}}
        s = bakeoff.score([run], truth)
        self.assertEqual((s["false_conflicts"], s["sent_to_review"], s["missed_conflicts"]), (1, 1, 1))
        self.assertEqual((s["a_false_conflicts"], s["a_missed_conflicts"]), (1, 1))
        self.assertEqual((s["unknown"], s["active"]), (1, 11))


if __name__ == "__main__":
    unittest.main()
