"""Adapter layer: the model asserts, the pipeline verifies."""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.adapter import run_extraction
from pfia.adapter.base import AdapterError
from pfia.adapter.payload import anti_pattern_hits, normalize_response, verify
from pfia.adapter.prompt import build, response_schema
from pfia.adapter.providers import HeuristicAdapter, ReplayAdapter
from pfia.adapter.retrieval import sweep
from pfia.evaluate import review
from pfia.extraction import PrecomputedExtractor

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE / "data" / "registers"
FIX = BASE / "tests" / "fixtures"


def _read(name):
    return (FIX / name).read_text(encoding="utf-8")


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TestPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.control = cls.rs.control("TX-PFIA-2256.005-b-4-E-001")

    def test_prompt_is_derived_from_the_control(self):
        from pfia.adapter.prompt import asked_elements

        prompt = build(self.control, [(0, "some window text")])
        asked = asked_elements(self.control)
        self.assertTrue(asked)
        for element in asked:
            self.assertIn(element.assertion, prompt)
        self.assertIn(self.control.cite_label, prompt)

    def test_negative_elements_are_never_put_to_the_model(self):
        """There is no passage to quote for a proposition satisfied by absence, so asking
        invites a fabricated one."""
        prompt = build(self.control, [(0, "some window text")])
        negatives = [e for e in self.control.elements if e.negative]
        self.assertTrue(negatives, "the DVP carve-out element should be negative")
        for element in negatives:
            self.assertNotIn(element.assertion, prompt)

    def test_prompt_withholds_verdicts_severity_and_anti_patterns(self):
        prompt = build(self.control, [(0, "some window text")])
        for leak in ("CONFORMING", "DEFICIENT", "ABSENT", self.control.severity):
            self.assertNotIn(leak, prompt)
        for pattern in self.control.test["anti_patterns"]:
            self.assertNotIn(pattern, prompt)

    def test_response_schema_enumerates_only_the_asked_elements(self):
        from pfia.adapter.prompt import asked_elements

        schema = response_schema(self.control)
        allowed = schema["properties"]["elements"]["items"]["properties"]["id"]["enum"]
        self.assertEqual(set(allowed), {e.id for e in asked_elements(self.control)})

    def test_facts_block_appears_only_for_structured_controls(self):
        structured = self.rs.control("IS-2256.013-001")
        self.assertIn("facts", response_schema(structured)["properties"])
        self.assertNotIn("facts", response_schema(self.control)["properties"])


class TestSpanVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.control = cls.rs.control("TX-PFIA-2256.005-b-4-E-001")
        cls.document = _read("policy_conforming.txt")

    def _verify(self, elements, facts=None):
        raw = {"elements": elements}
        if facts:
            raw["facts"] = facts
        return verify(self.control, normalize_response(self.control, raw), self.document)

    def test_verified_quote_yields_real_offsets(self):
        quote = "settled on a delivery versus payment basis"
        entry = self._verify([{"id": "e1", "supported": True, "quote": quote}])
        self.assertTrue(entry["elements_satisfied"]["e1"])
        start, end = entry["spans"]["e1"][0]
        self.assertEqual(self.document[start:end].lower(), quote.lower())

    def test_fabricated_quote_is_discarded_not_trusted(self):
        entry = self._verify([{"id": "e1", "supported": True,
                               "quote": "the Authority settles all trades through a central clearinghouse"}])
        self.assertFalse(entry["elements_satisfied"]["e1"])
        self.assertNotIn("e1", entry["spans"])
        self.assertTrue(any("not found in the document" in t for t in entry["retrieval_trace"]))

    def test_support_claimed_without_a_quote_is_discarded(self):
        entry = self._verify([{"id": "e1", "supported": True, "quote": "   "}])
        self.assertFalse(entry["elements_satisfied"]["e1"])
        self.assertTrue(any("without a quote" in t for t in entry["retrieval_trace"]))

    def test_unknown_element_ids_are_dropped(self):
        response = normalize_response(self.control, {"elements": [{"id": "e99", "supported": True}]})
        self.assertEqual(response.elements, [])

    def test_missing_claim_defaults_to_unsupported(self):
        entry = self._verify([])
        self.assertFalse(any(entry["elements_satisfied"].values()))

    def test_quote_matching_survives_line_wrapping(self):
        # The fixture wraps this phrase mid-sentence; a naive literal match would miss it.
        quote = "All securities transactions, other than investment pool funds and mutual funds"
        entry = self._verify([{"id": "e1", "supported": True, "quote": quote}])
        self.assertTrue(entry["elements_satisfied"]["e1"])

    def test_anti_patterns_are_found_without_the_model(self):
        deficient = _read("policy_deficient.txt")
        hits = anti_pattern_hits(self.control, deficient)
        self.assertTrue(hits)
        self.assertEqual(deficient[hits[0][0]:hits[0][1]].lower().split()[0], "where")


class TestRetrievalSweep(unittest.TestCase):
    def test_no_directive_match_establishes_absence(self):
        result = sweep("nothing relevant here at all", ["delivery versus payment", "DVP"])
        self.assertFalse(result.matched)
        self.assertEqual(result.windows, [])
        self.assertTrue(any("absence established" in t for t in result.trace))

    def test_matches_yield_merged_windows_with_offsets(self):
        document = "x" * 500 + " delivery versus payment " + "y" * 500
        result = sweep(document, ["delivery versus payment"])
        self.assertTrue(result.matched)
        offset, text = result.windows[0]
        self.assertIn("delivery versus payment", text)
        self.assertGreater(offset, 0)


class _ExplodingAdapter:
    name = "exploding"

    def ask(self, prompt, control_id, response_schema):
        raise AdapterError("provider unavailable")


class TestRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)
        cls.profile = _json(BASE / "data" / "profiles" / "water_authority.json")
        cls.facts = _json(FIX / "facts_water_authority.json")
        cls.document = _read("policy_conforming.txt")
        cls.extraction = run_extraction(cls.rs, HeuristicAdapter(), cls.document, cls.profile, cls.facts)

    def test_prefilter_covers_every_control_scored_from_extraction(self):
        """The runner may extract more than the evaluator scores, never less.

        The only permitted gap is the prohibition controls, whose verdicts come from the
        authorized-instrument set rather than from the document.
        """
        result = review(self.rs, self.profile, self.facts, self.document,
                        PrecomputedExtractor(self.extraction.payload, source="test"))
        scored = {f.control_id for f in result.in_scope()}
        gap = scored - set(self.extraction.payload)
        for control_id in gap:
            self.assertTrue(self.rs.control(control_id).inverted, control_id)

    def test_prohibition_controls_never_cost_a_model_call(self):
        inverted = {c.control_id for c in self.rs.controls if c.inverted}
        self.assertTrue(inverted)
        self.assertFalse(inverted & set(self.extraction.payload))

    def test_absence_is_resolved_without_a_model_call(self):
        self.assertGreater(self.extraction.skipped_absent, 0)
        self.assertEqual(self.extraction.calls + self.extraction.context_calls + self.extraction.skipped_absent,
                         len(self.extraction.payload))

    def test_every_payload_entry_carries_a_trace(self):
        for control_id, entry in self.extraction.payload.items():
            self.assertTrue(entry["retrieval_trace"], control_id)
            self.assertIn("anti_pattern_hits", entry)

    def test_adapter_failure_degrades_one_control_not_the_run(self):
        run = run_extraction(self.rs, _ExplodingAdapter(), self.document, self.profile, self.facts)
        self.assertTrue(run.failures)
        self.assertTrue(run.payload)
        for control_id in run.failures:
            entry = run.payload[control_id]
            self.assertFalse(any(entry["elements_satisfied"].values()))
            self.assertTrue(any("adapter failure" in t for t in entry["retrieval_trace"]))

    def test_cache_eliminates_repeat_calls(self):
        import tempfile

        with tempfile.TemporaryDirectory() as cache:
            first = run_extraction(self.rs, HeuristicAdapter(), self.document, self.profile,
                                   self.facts, cache_dir=cache)
            second = run_extraction(self.rs, HeuristicAdapter(), self.document, self.profile,
                                    self.facts, cache_dir=cache)
            self.assertGreater(first.calls, 0)
            self.assertEqual(second.calls, 0)
            self.assertEqual(second.cache_hits, first.calls + first.context_calls)
            self.assertEqual(first.payload, second.payload)

    def test_context_controls_never_reach_the_live_adapter(self):
        """ADR 0011: at SUMMARY depth Context controls are answered offline."""
        seen = []

        class _Spy(HeuristicAdapter):
            name = "live-spy"

            def ask(self, prompt, control_id, schema):
                seen.append(control_id)
                return super().ask(prompt, control_id, schema)

        run = run_extraction(self.rs, _Spy(), self.document, self.profile, self.facts)
        context = {c.control_id for c in self.rs.controls if c.relevance == "CONTEXT"}
        self.assertFalse(context & set(seen))
        self.assertTrue(set(run.context_controls) <= context)
        full = run_extraction(self.rs, _Spy(), self.document, self.profile, self.facts, context_depth="FULL")
        self.assertEqual(full.context_controls, [])

    def test_replay_adapter_returns_recorded_answers(self):
        cassette = {"TX-PFIA-2256.005-b-4-E-001": {"elements": [
            {"id": "e1", "supported": True,
             "quote": "settled on a delivery versus payment basis"}]}}
        run = run_extraction(self.rs, ReplayAdapter(cassette, name="fixture"), self.document,
                             self.profile, self.facts)
        entry = run.payload["TX-PFIA-2256.005-b-4-E-001"]
        self.assertTrue(entry["elements_satisfied"]["e1"])
        # e2 is negative and resolved deterministically, so the cassette has no say in it.
        self.assertNotIn("e2", {c["element_id"] for c in entry.get("discarded_claims", [])})


if __name__ == "__main__":
    unittest.main()


class TestPayloadShapes(unittest.TestCase):
    """Providers vary the wrapper. The content is what matters.

    Asked for "one entry per element id", a model will sometimes return the array on its
    own. That is a missing wrapper, not a bad answer, and wrapping it is the right repair.
    Anything genuinely unusable must fail with the observed keys rather than surfacing as
    an AttributeError three frames downstream.
    """

    def _parse(self, text):
        from pfia.adapter.providers.http_json import _parse_json_object

        return _parse_json_object(text)

    def test_bare_array_is_wrapped(self):
        payload = self._parse('[{"id":"e1","supported":true,"quote":"x"}]')
        self.assertEqual(payload["elements"][0]["id"], "e1")

    def test_object_passes_through_with_facts(self):
        payload = self._parse('{"elements":[{"id":"e1","supported":true}],"facts":{"max_maturity_days":270}}')
        self.assertEqual(payload["facts"]["max_maturity_days"], 270)

    def test_single_wrapper_key_is_unwrapped(self):
        payload = self._parse('{"results":[{"id":"e1","supported":true}]}')
        self.assertEqual(len(payload["elements"]), 1)

    def test_results_keyed_by_element_id_are_relisted(self):
        payload = self._parse('{"e1":{"supported":true,"quote":"x"},"e2":{"supported":false}}')
        self.assertEqual({e["id"] for e in payload["elements"]}, {"e1", "e2"})

    def test_code_fence_and_prose_prefix_are_tolerated(self):
        for text in ('```json\n[{"id":"e1","supported":false}]\n```',
                     'Here is the result: [{"id":"e1","supported":true}]'):
            with self.subTest(text=text[:20]):
                self.assertEqual(len(self._parse(text)["elements"]), 1)

    def test_unusable_shape_names_what_it_saw(self):
        with self.assertRaises(AdapterError) as ctx:
            self._parse('{"verdict":"CONFORMING"}')
        self.assertIn("elements", str(ctx.exception))

    def test_prose_only_response_fails_clearly(self):
        with self.assertRaises(AdapterError):
            self._parse("I cannot answer that.")

    def test_normalize_response_tolerates_a_bare_array(self):
        """The convergence point for cached, replayed and live payloads alike."""
        rs = loader.load(ROOT)
        control = rs.control("TX-PFIA-2256.005-b-4-E-001")
        response = normalize_response(control, [{"id": "e1", "supported": True, "quote": "x"}])
        self.assertEqual(len(response.elements), 1)

    def test_normalize_response_rejects_a_scalar(self):
        from pfia.errors import ExtractionError

        rs = loader.load(ROOT)
        control = rs.control("TX-PFIA-2256.005-b-4-E-001")
        with self.assertRaises(ExtractionError):
            normalize_response(control, "CONFORMING")


class TestTruncationAndKeyNames(unittest.TestCase):
    """A response that ran out of budget is incomplete, not wrong.

    Both defects here came from one real run: the model used `element_id` rather than `id`,
    and the response stopped mid-array when it hit the token ceiling. Either alone loses a
    whole control's worth of paid-for, correct answers.
    """

    def _parse(self, text):
        from pfia.adapter.providers.http_json import _parse_json_object

        return _parse_json_object(text)

    def test_element_id_synonyms_are_accepted(self):
        rs = loader.load(ROOT)
        control = rs.control("TX-PFIA-2256.005-b-4-E-001")
        for key in ("id", "element_id", "elementId", "element"):
            with self.subTest(key=key):
                response = normalize_response(control, {"elements": [
                    {key: "e1", "supported": True, "quote": "x"}]})
                self.assertEqual([e.element_id for e in response.elements], ["e1"])

    def test_truncated_array_is_salvaged_and_flagged(self):
        payload = self._parse(
            '[\n {"element_id":"e1","supported":true,"quote":"alpha"},\n'
            '  {"element_id":"e2","supported":false},\n  {"element_id":"e3","suppor'
        )
        self.assertEqual(len(payload["elements"]), 2)
        self.assertTrue(payload["_truncated"])

    def test_salvage_ignores_braces_inside_quoted_text(self):
        """Brace counting must respect string literals, or a quoted brace ends an object
        early and the salvaged text is silently wrong."""
        import json as _json

        good = {"element_id": "e1", "supported": True,
                "quote": 'a } brace and a "quoted" phrase'}
        text = "[" + _json.dumps(good) + ',{"element_id":"e2","supported":fal'
        payload = self._parse(text)
        self.assertEqual(len(payload["elements"]), 1)
        self.assertEqual(payload["elements"][0]["quote"], good["quote"])

    def test_salvage_requires_a_supported_field(self):
        """Stray objects that are not element results must not be mistaken for them."""
        from pfia.adapter.base import AdapterError

        with self.assertRaises(AdapterError):
            self._parse('{"usage":{"input_tokens":12}} trailing junk')

    def test_missing_elements_default_to_unsupported_after_salvage(self):
        rs = loader.load(ROOT)
        control = rs.control("TX-PFIA-2256.005-b-3-001")
        document = "Diversification: the entity will diversify by sector and maturity."
        payload = self._parse(
            '[{"element_id":"e1","supported":true,'
            '"quote":"the entity will diversify by sector and maturity"},{"element_id":"e2"'
        )
        entry = verify(control, normalize_response(control, payload), document)
        self.assertTrue(entry["elements_satisfied"]["e1"])
        for element_id in ("e2", "e3", "e4"):
            self.assertFalse(entry["elements_satisfied"][element_id])
        self.assertTrue(any("no claim returned" in t for t in entry["retrieval_trace"]))

    def test_truncation_reaches_the_run_summary(self):
        from pfia.adapter.providers.replay import ReplayAdapter

        rs = loader.load(ROOT)
        document = _read("policy_conforming.txt")
        cassette = {"TX-PFIA-2256.005-b-4-E-001": {
            "elements": [{"element_id": "e1", "supported": True,
                          "quote": "settled on a delivery versus payment basis"}],
            "_truncated": True,
        }}
        run = run_extraction(
            rs, ReplayAdapter(cassette, name="fixture"), document,
            _json(BASE / "data" / "profiles" / "water_authority.json"),
            _json(FIX / "facts_water_authority.json"),
        )
        self.assertIn("TX-PFIA-2256.005-b-4-E-001", run.truncated)
        self.assertIn("truncated", run.summary())


class TestContextAndCrossReferences(unittest.TestCase):
    """A well-drafted policy points at its own collateral section rather than repeating it.

    Showing the model only the clause that made the reference guarantees a finding of
    absence against a policy that addressed the point properly, just not in that
    paragraph. Widening must not make absence unprovable, though, or every control finds
    something somewhere.
    """

    def _sweep(self, document, directives, context=None):
        from pfia.adapter.retrieval import sweep

        return sweep(document, directives, context or [])

    def test_context_directives_widen_the_windows(self):
        document = ("A. REPURCHASE AGREEMENTS. Collateralized in accordance with this policy.\n\n"
                    + "filler " * 300
                    + "\n\nB. COLLATERAL. Collateral is held by a third party custodian.\n")
        narrow = self._sweep(document, ["repurchase agreement"])
        wide = self._sweep(document, ["repurchase agreement"], ["third party custodian"])
        self.assertTrue(narrow.matched and wide.matched)
        self.assertGreater(len(wide.windows), len(narrow.windows))
        self.assertTrue(any("custodian" in text for _offset, text in wide.windows))

    def test_context_directives_cannot_establish_a_match(self):
        document = "B. COLLATERAL. Collateral is held by a third party custodian.\n"
        result = self._sweep(document, ["repurchase agreement"], ["third party custodian"])
        self.assertFalse(result.matched)
        self.assertEqual(result.windows, [])

    def test_a_cross_reference_is_followed(self):
        document = ("IV. AUTHORIZED INVESTMENTS. Certificates of deposit secured by "
                    "obligations described in Section VI (B) of this Investment Policy.\n\n"
                    + "filler " * 300
                    + "\n\nSection VI (B). Eligible collateral is limited to obligations of "
                    "the United States at a market value not less than principal.\n")
        result = self._sweep(document, ["certificates of deposit"])
        self.assertTrue(any("Eligible collateral" in text for _offset, text in result.windows))
        self.assertTrue(any("followed cross-reference" in line for line in result.trace))

    def test_following_does_not_loop_on_a_self_reference(self):
        document = "Section IV (A). See Section IV (A) for details.\n"
        result = self._sweep(document, ["Section IV"])
        self.assertTrue(result.matched)
        self.assertLessEqual(len(result.windows), 10)
