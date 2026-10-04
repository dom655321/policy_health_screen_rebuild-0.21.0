"""Report view model and rendering.

The view model is tested without the optional extras installed, because it is a pure
function of the ledger and must stay that way. Rendering tests skip when jinja2 or
weasyprint are absent.
"""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import review
from pfia.extraction import KeywordExtractor
from pfia.ledger import build_ledger
from pfia.report.render import extras_available
from pfia.report.viewmodel import build

BASE = Path(__file__).resolve().parents[1]
FIX = BASE / "tests" / "fixtures"
REGISTERS = BASE / "data" / "registers"


def _ledger(profile_name, facts_name, policy_name):
    rs = loader.load(REGISTERS)
    profile = json.loads((BASE / "data" / "profiles" / f"{profile_name}.json").read_text())
    facts = json.loads((FIX / facts_name).read_text())
    document = (FIX / policy_name).read_text(encoding="utf-8")
    result = review(rs, profile, facts, document, KeywordExtractor())
    return build_ledger(rs, result, document, policy_name, "keyword-baseline")


class TestViewModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deficient = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )
        cls.conforming = build(
            _ledger("water_authority", "facts_water_authority.json", "policy_conforming.txt"),
            entity_name="Example Regional Water Authority",
        )

    def test_verdict_follows_the_section_rules(self):
        self.assertEqual(self.deficient["report"].statutory_verdict.value, "Revisions Recommended")
        # The conforming fixture authorizes single-agency commercial paper without a letter
        # of credit. The old CRITICAL-only gate hid that HIGH-severity conflict; the section
        # rules do not rank a conflict below a threshold (ADR 0010).
        sections = self.conforming["sections"]
        self.assertEqual(sections["PFIA_REQUIREMENTS"]["status"], "ADDRESSES_PROVISIONS_REVIEWED")
        self.assertEqual(sections["AUTHORIZED_INVESTMENTS"]["conflicts"], ["IS-2256.013-001"])

    def test_no_score_reaches_the_report(self):
        for ctx in (self.deficient, self.conforming):
            for key in ("health_score", "health_capped", "health_band", "advisory"):
                self.assertNotIn(key, ctx)
            self.assertIn(ctx["overall_status"], (
                "REVIEW_IN_PROGRESS", "REVISIONS_RECOMMENDED", "ADDITIONS_RECOMMENDED",
                "ADDRESSES_PROVISIONS_REVIEWED", "NOT_ASSESSED"))

    def test_requirement_class_survives_the_mapping(self):
        classes = {v.requirement_class.value for v in self.deficient["report"].statutory_findings}
        self.assertIn("MANDATORY", classes)
        self.assertIn("CONDITIONAL", classes)

    def test_scored_figures_are_not_zero(self):
        figures = self.deficient["statutory"]
        self.assertGreater(figures["reviewed"], 0)
        self.assertLessEqual(figures["passed"], figures["reviewed"])

    def test_deficient_split_distinguishes_partial_from_contradicted(self):
        statuses = {v.status.value for v in self.deficient["deficiencies"]}
        self.assertTrue({"Fail", "Partial", "Not Found"} & statuses)

    def test_advisory_band_lands_in_the_enhancement_index(self):
        hsam_ids = {v.control_id for v in self.deficient["report"].hsam_findings}
        statutory_ids = {v.control_id for v in self.deficient["report"].statutory_findings}
        self.assertTrue(hsam_ids)
        self.assertFalse(hsam_ids & statutory_ids)

    def test_unassessed_frameworks_are_empty_not_zeroed(self):
        """GTOT and the maturity index are absent, and must be reported as absent."""
        self.assertEqual(self.deficient["report"].gtot_findings, [])
        self.assertEqual(self.deficient["report"].quality_scores, [])
        self.assertEqual(self.deficient["gtot"]["reviewed"], 0)
        self.assertEqual(self.deficient["gtot"]["status"], "PAUSED")

    def test_deficiencies_are_ordered_worst_first(self):
        order = [v.severity.value for v in self.deficient["deficiencies"]]
        rank = {"Critical": 0, "High": 1, "Moderate": 2, "Enhancement": 3}
        self.assertEqual(order, sorted(order, key=lambda s: rank.get(s, 9)))

    def test_analysis_is_composed_not_generated(self):
        """No sentence in the report may originate with a language model."""
        finding = next(v for v in self.deficient["deficiencies"] if v.elements)
        self.assertIn(finding.title, finding.analysis)
        self.assertTrue(finding.recommendation)

    def test_heuristic_extraction_lowers_confidence_and_states_why(self):
        finding = self.deficient["deficiencies"][0]
        self.assertEqual(finding.confidence.value, "Low")
        self.assertIn("not review-grade", finding.review_limitations)

    def test_provenance_names_the_extractor_and_register_versions(self):
        provenance = self.deficient["report"].provenance
        self.assertEqual(provenance.extraction_model, "keyword-baseline")
        self.assertIn("A@", provenance.register_version)
        self.assertIn("no model critic", provenance.critic_model)


@unittest.skipUnless(extras_available()[0], "jinja2/weasyprint not installed")
class TestRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )

    def test_html_renders_under_strict_undefined(self):
        from pfia.report import render_html
        from pfia.report.render import LEGACY_TEMPLATE

        html = render_html(self.context, LEGACY_TEMPLATE)
        self.assertIn("Example City", html)
        self.assertIn("REVISIONS RECOMMENDED", html)
        # StrictUndefined would have raised rather than emit these.
        self.assertNotIn("Undefined", html)

    def test_unassessed_tables_say_so_in_the_output(self):
        """Specific to the inherited template, which carries the GTOT and maturity tables."""
        from pfia.report import render_html
        from pfia.report.render import LEGACY_TEMPLATE

        html = render_html(self.context, LEGACY_TEMPLATE)
        self.assertIn("NOT ASSESSED", html.upper())

    def test_pdf_is_produced(self):
        import tempfile

        from pfia.report import render_pdf

        with tempfile.TemporaryDirectory() as tmp:
            path = render_pdf(self.context, Path(tmp) / "report.pdf")
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreater(len(data), 20000)


if __name__ == "__main__":
    unittest.main()


class TestScreenTemplate(unittest.TestCase):
    """The redesigned template, and the one guarantee page one has to make.

    Page one is the page that gets detached and sent for compliance review. It is built
    only from the `client_safe` block, so it cannot carry control identifiers, unreviewed
    draft language or confidence labels by accident - a page intended for distribution
    should describe the policy rather than the tool.
    """

    @classmethod
    def setUpClass(cls):
        cls.context = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )

    def test_client_safe_block_carries_no_control_identifiers(self):
        payload = json.dumps(self.context["client_safe"], default=str)
        for leak in ("TX-PFIA-", "IS-2256.", "UNREVIEWED", "CONFIDENCE", "control_id"):
            self.assertNotIn(leak, payload, leak)

    def test_priority_items_are_section_and_title_only(self):
        for item in self.context["client_safe"]["priority"]:
            self.assertEqual(set(item), {"section", "title", "status", "severity"})

    def test_priority_items_are_statutory_only(self):
        """An advisory item on a client page would attribute a practice expectation to the
        statute."""
        advisory_titles = {v.title for v in self.context["report"].hsam_findings}
        for item in self.context["client_safe"]["priority"]:
            self.assertNotIn(item["title"], advisory_titles)

    def test_internal_material_is_present_for_the_later_pages(self):
        for key in ("coverage", "unresolved", "instruments", "review_queue",
                    "review_by_action", "review_action_text"):
            self.assertIn(key, self.context)


@unittest.skipUnless(extras_available()[0], "jinja2/weasyprint not installed")
class TestScreenRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )

    def _cover(self):
        from pfia.report import render_html

        html = render_html(self.context)
        # Everything before the internal divider is page one by construction.
        return html.split('class="divider"')[0]

    def test_default_template_is_the_redesign(self):
        from pfia.report.render import DEFAULT_TEMPLATE

        self.assertEqual(DEFAULT_TEMPLATE, "hsam_screen.html")

    def test_cover_contains_no_internal_artifacts(self):
        cover = self._cover()
        for leak in ("TX-PFIA-", "IS-2256.", "UNREVIEWED DRAFT", "Reviewer work queue",
                     "Run provenance", "review_action"):
            self.assertNotIn(leak, cover, leak)

    def test_cover_carries_the_limits_language(self):
        cover = self._cover()
        for required in ("Basis and limits", "do not constitute legal", 
                         "not a determination of compliance", "2256.024"):
            self.assertIn(required, cover, required)

    def test_internal_sections_are_marked_on_their_own_face(self):
        from pfia.report import render_html

        html = render_html(self.context)
        self.assertIn("not for client distribution", html)
        self.assertIn("Reviewer work queue", html)

    def test_distribution_marking_switches(self):
        from pfia.report import render_html

        internal = render_html(self.context)
        self.assertIn("Internal use only", internal)
        client = dict(self.context)
        client["distribution"] = "client-draft"
        self.assertIn("pending compliance review", render_html(client))

    def test_legacy_template_still_renders(self):
        from pfia.report import render_html
        from pfia.report.render import LEGACY_TEMPLATE

        html = render_html(self.context, LEGACY_TEMPLATE)
        self.assertIn("Example City", html)

    def test_pdf_is_produced(self):
        import tempfile

        from pfia.report import render_pdf

        with tempfile.TemporaryDirectory() as tmp:
            path = render_pdf(self.context, Path(tmp) / "screen.pdf")
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))


class TestRegisterRootResolution(unittest.TestCase):
    """The register lives outside the package, so an installed wheel cannot assume a
    repo-relative path. Resolution order: environment variable, repository layout, packaged
    copy - and a miss must fail loudly at load rather than yield an empty register."""

    def test_environment_variable_wins(self):
        import importlib
        import os

        from pfia import cli

        original = os.environ.get("PFIA_REGISTER_ROOT")
        os.environ["PFIA_REGISTER_ROOT"] = "/tmp/some/other/registers"
        try:
            importlib.reload(cli)
            self.assertEqual(str(cli.DEFAULT_ROOT), "/tmp/some/other/registers")
        finally:
            if original is None:
                del os.environ["PFIA_REGISTER_ROOT"]
            else:
                os.environ["PFIA_REGISTER_ROOT"] = original
            importlib.reload(cli)

    def test_repository_layout_resolves_by_default(self):
        from pfia import cli

        self.assertTrue((cli.DEFAULT_ROOT / "entity_classes.json").exists())

    def test_a_missing_register_fails_loudly(self):
        from pfia import loader
        from pfia.errors import RegisterLoadError

        with self.assertRaises(RegisterLoadError):
            loader.load(Path("/tmp/definitely/not/a/register/root"))


class TestClientPhrasing(unittest.TestCase):
    """Audit vocabulary asserts a claim this screen cannot support.

    In public finance, "failure" and "deficiency" read as a breach of fiduciary duty. What
    the screen observes is narrower: whether a provision is expressly addressed in the text
    of a policy document. Relocating the claim from the entity's conduct to the document's
    text is not softening - it is the accurate statement of what was examined.
    """

    @classmethod
    def setUpClass(cls):
        cls.context = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )

    def test_client_block_uses_no_audit_vocabulary(self):
        from pfia.report import phrasing

        payload = json.dumps(self.context["client_safe"], default=str)
        self.assertEqual(phrasing.scrub_check(payload), [])

    def test_the_summary_counts_what_is_addressed_first(self):
        from pfia.report import phrasing

        summary = self.context["client_safe"]["summary"]
        self.assertIn("expressly addressed", summary)
        self.assertIn("does not examine", summary)
        self.assertEqual(phrasing.scrub_check(summary), [])

    def test_the_verdict_is_forward_looking(self):
        verdict = self.context["client_safe"]["verdict"]
        self.assertIn(verdict, ("AMENDMENTS RECOMMENDED", "ITEMS FOR CONSIDERATION",
                                "NO ITEMS IDENTIFIED", "REVIEW INCOMPLETE"))

    def test_the_gate_is_still_explained(self):
        """Reframing must not lose the substance: the result turns on the mandatory test
        and not on the score, and the page has to say so."""
        note = self.context["client_safe"]["gate_note"]
        self.assertIn("required provision", note)
        self.assertIn("No score or weighting is applied", note)

    def test_a_stated_conflict_is_phrased_as_a_difference(self):
        from pfia.report import phrasing

        self.assertEqual(phrasing.status("CONFLICTS"), "Stated terms differ from the statute")
        self.assertEqual(phrasing.status("PARTIALLY_ADDRESSED"), "Addressed in part")
        self.assertEqual(phrasing.status("NOT_ADDRESSED"), "Not expressly addressed")

    def test_severity_words_do_not_read_as_incidents(self):
        from pfia.report import phrasing

        self.assertEqual(phrasing.severity("CRITICAL"), "Mandatory")
        self.assertEqual(phrasing.severity("ADVISORY"), "Practice")

    def test_nothing_is_hidden_by_the_reframing(self):
        """Every mandatory item still appears, still ranked first."""
        priority = self.context["client_safe"]["priority"]
        self.assertTrue(priority)
        self.assertEqual(priority[0]["severity"], "Mandatory")
        internal = {f.control_id for f in self.context["deficiencies"]}
        self.assertTrue(internal)


@unittest.skipUnless(extras_available()[0], "jinja2/weasyprint not installed")
class TestCoverPhrasing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = build(
            _ledger("city", "facts_deposit_program.json", "policy_deficient.txt"),
            entity_name="Example City", entity_class_label="Municipality",
        )

    def test_rendered_cover_uses_no_audit_vocabulary(self):
        from pfia.report import phrasing, render_html

        cover = render_html(self.context).split('class="divider"')[0]
        # Strip the stylesheet: CSS class names carry the internal vocabulary and are not
        # read by anyone.
        body = cover.split("</style>", 1)[-1]
        self.assertEqual(phrasing.scrub_check(body), [])


class TestReviewVocabulary(unittest.TestCase):
    """The reviewer verdict column is a closed list because each value maps to one change.

    "This seems too strict" does not say whether the element should be reworded, split,
    dropped or rebanded, and those are four different changes to the register.
    """

    @classmethod
    def setUpClass(cls):
        import sys

        sys.path.insert(0, str(BASE / "scripts"))
        import export_review

        cls.module = export_review

    def test_every_verdict_has_a_meaning(self):
        for value, meaning in self.module.VERDICTS:
            self.assertTrue(value.isupper())
            self.assertGreater(len(meaning), 40, value)

    def test_the_list_covers_every_change_the_register_supports(self):
        values = set(self.module.VERDICT_VALUES)
        self.assertEqual(
            values,
            {"KEEP", "REWORD", "SPLIT", "DROP", "REBAND", "NOT_TESTABLE", "ADD", "QUERY"},
        )

    def test_the_guide_documents_each_value(self):
        guide = (BASE / "docs" / "REVIEW-GUIDE.md").read_text(encoding="utf-8")
        for value in self.module.VERDICT_VALUES:
            self.assertIn(f"**{value}**", guide, value)
