"""Entity profile: derived questions, and unanswered questions that stay unanswered."""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import APPLICABILITY_UNRESOLVED, review
from pfia.extraction import NullExtractor
from pfia.jsonlogic import UNKNOWN, PredicateError
from pfia.profile import (
    ProfileError, build_context, dependants, impact, load, load_field_specs, questionnaire,
    reconcile, required_paths,
)

BASE = Path(__file__).resolve().parents[1]
REGISTERS = BASE / "data" / "registers"
PROFILES = BASE / "data" / "profiles"


class TestFieldDerivation(unittest.TestCase):
    """The questionnaire is derived from the register and cannot drift from it."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.specs = load_field_specs(PROFILES)

    def test_every_consumed_fact_has_a_question(self):
        missing, _ = reconcile(self.rs, self.specs)
        self.assertEqual(missing, set(), f"register reads facts with no question: {missing}")

    def test_every_question_has_a_consumer(self):
        _, orphaned = reconcile(self.rs, self.specs)
        self.assertEqual(orphaned, set(), f"questions nothing reads: {orphaned}")

    def test_derivation_finds_facts_in_predicates_and_inline_logic(self):
        paths = required_paths(self.rs)
        self.assertIn("entity.classes", paths)
        self.assertIn("entity.exclusions.public_retirement_system_802_001", paths)
        self.assertIn("entity.has_pooled_fund_groups", paths)

    def test_dependency_map_names_real_controls(self):
        known = {c.control_id for c in self.rs.controls}
        for _path, controls in dependants(self.rs, required_paths(self.rs)).items():
            self.assertTrue(set(controls) <= known)

    def test_questionnaire_covers_every_question_with_its_dependants(self):
        blank = questionnaire(self.rs, self.specs, "Test Entity")
        questions = blank["_questions"]
        self.assertEqual(len(questions), len(self.specs) - 1)  # classes is asked separately
        pooled = questions["entity.has_pooled_fund_groups"]
        self.assertIn("TX-PFIA-2256.005-b-4-C-001", pooled["controls_that_depend_on_it"])
        self.assertTrue(pooled["question"])
        self.assertTrue(pooled["cite"])


class TestUnansweredFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.specs = load_field_specs(PROFILES)
        cls.complete = json.loads((PROFILES / "city.json").read_text())

    def _context(self, **overrides):
        profile = dict(self.complete)
        profile.update(overrides)
        return build_context(self.rs, profile, self.specs)

    def test_unanswered_becomes_unknown_not_false(self):
        entity, report = self._context(has_pooled_fund_groups=None)
        self.assertIs(entity["has_pooled_fund_groups"], UNKNOWN)
        self.assertIn("entity.has_pooled_fund_groups", report.unanswered)
        self.assertFalse(report.complete)

    def test_unknown_refuses_to_be_treated_as_a_boolean(self):
        with self.assertRaises(PredicateError):
            bool(UNKNOWN)

    def test_classes_cannot_be_left_unanswered(self):
        with self.assertRaises(ProfileError):
            build_context(self.rs, {"classes": []}, self.specs)

    def test_one_unanswered_fact_unresolves_only_its_dependants(self):
        entity, _ = self._context(has_pooled_fund_groups=None)
        facts = {"authorized_instruments": ["US_OBLIGATIONS"]}
        result = review(self.rs, entity, facts, "", NullExtractor())
        by_id = {f.control_id: f for f in result.findings}
        self.assertEqual(by_id["TX-PFIA-2256.005-b-4-C-001"].verdict, APPLICABILITY_UNRESOLVED)
        self.assertNotEqual(by_id["TX-PFIA-2256.005-a-001"].verdict, APPLICABILITY_UNRESOLVED)

    def test_unanswered_applicability_gate_unresolves_everything(self):
        profile = dict(self.complete)
        profile["exclusions"] = {k: None for k in profile["exclusions"]}
        entity, _ = build_context(self.rs, profile, self.specs)
        result = review(self.rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        self.assertEqual(len(result.unresolved()), len(result.findings))
        self.assertEqual(len(result.in_scope()), 0)

    def test_nothing_scored_is_not_a_perfect_score(self):
        profile = dict(self.complete)
        profile["exclusions"] = {k: None for k in profile["exclusions"]}
        entity, _ = build_context(self.rs, profile, self.specs)
        result = review(self.rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        for section in result.sections().values():
            self.assertIn(section["status"], ("REVIEW_IN_PROGRESS", "NOT_ASSESSED", "SUMMARIZED"))
            self.assertEqual(section["conflicts"] + section["additions"], [])

    def test_unresolved_controls_are_excluded_from_both_bands(self):
        entity, _ = self._context(has_pooled_fund_groups=None)
        result = review(self.rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        scored_ids = {f.control_id for f in result.in_scope()}
        unresolved_ids = {f.control_id for f in result.unresolved()}
        self.assertTrue(unresolved_ids)
        self.assertFalse(scored_ids & unresolved_ids)

    def test_unresolved_finding_names_the_unanswered_fact(self):
        entity, _ = self._context(investment_function_assigned_by_law=None)
        result = review(self.rs, entity, {"authorized_instruments": []}, "", NullExtractor())
        finding = next(f for f in result.findings if f.control_id == "TX-PFIA-2256.005-f-001")
        self.assertEqual(finding.verdict, APPLICABILITY_UNRESOLVED)
        self.assertIn("entity.investment_function_assigned_by_law", finding.unanswered_facts)

    def test_shipped_profiles_are_complete(self):
        for path in sorted(PROFILES.glob("*.json")):
            if path.name == "fields.json":
                continue
            with self.subTest(profile=path.name):
                _entity, report = load(self.rs, path, PROFILES)
                self.assertTrue(report.complete, f"{path.name}: {report.unanswered}")


if __name__ == "__main__":
    unittest.main()


class TestImpactReporting(unittest.TestCase):
    """A reviewer needs to know which blanks matter. Most do not."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.specs = load_field_specs(PROFILES)

    def _blank(self, classes):
        profile = {"classes": classes, "exclusions": {}}
        for spec in self.specs.values():
            if spec.path == "entity.classes":
                continue
            parts = spec.key.split(".")
            node = profile
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = None
        return profile

    def test_applicability_exclusions_gate_the_whole_register(self):
        effect = impact(self.rs, self._blank(["TOLLWAY_AUTHORITY"]), self.specs)
        for path in effect:
            if path.startswith("entity.exclusions."):
                self.assertEqual(len(effect[path]), len(self.rs.controls), path)

    def test_class_specific_questions_cost_nothing_for_other_classes(self):
        effect = impact(self.rs, self._blank(["TOLLWAY_AUTHORITY"]), self.specs)
        # The endowment threshold reaches institutions of higher education only.
        self.assertEqual(effect["entity.endowment_book_value_2017_09_01"], [])
        self.assertEqual(effect["entity.assets_invested_by_comptroller_404_024"], [])

    def test_a_single_field_can_isolate_a_single_control(self):
        effect = impact(self.rs, self._blank(["TOLLWAY_AUTHORITY"]), self.specs)
        self.assertEqual(effect["entity.has_pooled_fund_groups"], ["TX-PFIA-2256.005-b-4-C-001"])
        self.assertEqual(effect["entity.investment_function_assigned_by_law"],
                         ["TX-PFIA-2256.005-f-001"])

    def test_worst_case_instrument_set_is_assumed(self):
        """A field gating an unauthorized instrument must not be reported as harmless.

        Sec. 2256.0206 eligibility is a conjunction of a debt threshold and a rating test.
        With the rating limb answered false the conjunction is definitely false and the
        threshold no longer matters - correct Kleene behaviour, and the reason the impact
        report is sensitive to the placeholder used for the other blanks. Answer the rating
        limb affirmatively and the threshold becomes load-bearing.
        """
        profile = self._blank(["MUNICIPALITY"])
        profile["long_term_debt_rated_top_four"] = True
        effect = impact(self.rs, profile, self.specs)
        self.assertIn("IS-2256.0206-001", effect["entity.long_term_debt_principal"])

    def test_a_false_conjunct_makes_the_other_limb_moot(self):
        """The converse, stated as behaviour rather than left as a surprise."""
        profile = self._blank(["MUNICIPALITY"])
        profile["long_term_debt_rated_top_four"] = False
        effect = impact(self.rs, profile, self.specs)
        self.assertEqual(effect["entity.long_term_debt_principal"], [])

    def test_the_worked_example_profile_is_complete(self):
        _entity, report = load(self.rs, PROFILES / "EXAMPLE-tollway-authority.json", PROFILES)
        self.assertTrue(report.complete)


class TestAnswerValidation(unittest.TestCase):
    """Operator-edited profiles: helpful errors, harmless normalization, never a silent flip."""

    @classmethod
    def setUpClass(cls):
        import json as _json
        from pfia import profile as pm
        cls.pm = pm
        cls.rs = loader.load(BASE / "data" / "registers")
        cls.specs = pm.load_field_specs(BASE / "data" / "profiles")
        cls.base = _json.loads((BASE / "data" / "profiles" / "city.json").read_text(encoding="utf-8"))

    def _ctx(self, **changes):
        p = dict(self.base)
        p.update(changes)
        return self.pm.build_context(self.rs, p, self.specs)

    def test_yes_in_classes_names_the_problem(self):
        with self.assertRaisesRegex(self.pm.ProfileError, "looks like a yes/no answer"):
            self._ctx(classes="yes")
        with self.assertRaisesRegex(self.pm.ProfileError, "MUNICIPALITY"):
            self._ctx(classes=["y"])

    def test_close_class_id_is_suggested(self):
        with self.assertRaisesRegex(self.pm.ProfileError, "did you mean MUNICIPALITY"):
            self._ctx(classes=["MUNICIPALTY"])

    def test_lower_case_and_bare_string_ids_are_accepted_and_reported(self):
        entity, report = self._ctx(classes="municipality")
        self.assertIn("MUNICIPALITY", entity["classes"])
        self.assertTrue(any("MUNICIPALITY" in n for n in report.normalized))

    def test_yes_no_strings_become_booleans_and_are_reported(self):
        entity, report = self._ctx(has_pooled_fund_groups="No")
        self.assertIs(entity["has_pooled_fund_groups"], False)
        self.assertTrue(any("has_pooled_fund_groups" in n for n in report.normalized))

    def test_ambiguous_boolean_is_refused(self):
        with self.assertRaisesRegex(self.pm.ProfileError, "must be true or false"):
            self._ctx(has_pooled_fund_groups="maybe")

    def test_formatted_numbers_are_parsed(self):
        entity, _ = self._ctx(long_term_debt_principal="$250,000,000")
        self.assertEqual(entity["long_term_debt_principal"], 250000000.0)
        with self.assertRaisesRegex(self.pm.ProfileError, "must be a number"):
            self._ctx(long_term_debt_principal="a lot")

    def test_cli_reports_without_a_traceback(self):
        import json as _json
        import os
        import subprocess
        import sys
        import tempfile
        bad = dict(self.base, classes="yes")
        path = Path(tempfile.mkdtemp()) / "p.json"
        path.write_text(_json.dumps(bad), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pfia", "profile", "check", "--profile", str(path)],
                           cwd=BASE, env={**os.environ, "PYTHONPATH": str(BASE / "src")},
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("looks like a yes/no answer", r.stderr)
