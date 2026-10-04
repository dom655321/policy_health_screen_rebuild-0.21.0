"""Ingestion: the derived text must be faithful, traceable, and refused when unreadable."""

import json
import unittest
from pathlib import Path

from pfia import loader
from pfia.evaluate import review
from pfia.extraction import KeywordExtractor
from pfia.ingest import IngestError, SourceDocument, UnusableDocument, ingest_bytes, ingest_path
from pfia.ingest.normalize import normalize_page, strip_running_heads
from pfia.ingest.quality import assess
from pfia.ledger import build_ledger

BASE = Path(__file__).resolve().parents[1]
FIX = BASE / "tests" / "fixtures"
REGISTERS = BASE / "data" / "registers"
PDF = FIX / "policy_conforming.pdf"
TXT = FIX / "policy_conforming.txt"

KEY_PHRASES = [
    "delivery versus payment basis",
    "dollar-weighted average maturity",
    "prudence, discretion, and intelligence",
    "continuously rated no lower than AAA or AAA-m",
]


class TestNormalization(unittest.TestCase):
    def test_line_break_hyphen_is_joined(self):
        text, counts = normalize_page("settled on a delivery ver-\nsus payment basis.")
        self.assertIn("delivery versus payment basis", text)
        self.assertEqual(counts["line_break_hyphens_joined"], 1)

    def test_real_hyphens_survive(self):
        text, counts = normalize_page("the maximum dollar-weighted average maturity")
        self.assertIn("dollar-weighted", text)
        self.assertNotIn("line_break_hyphens_joined", counts)

    def test_capitalised_next_line_is_not_joined(self):
        # A line ending in a hyphen before a capital is far more likely a compound than a
        # broken word, so the conservative rule leaves it alone.
        text, _ = normalize_page("the Board approved AAA-\nRated pools")
        self.assertIn("AAA-\nRated", text)

    def test_ligatures_and_smart_punctuation_are_folded(self):
        text, counts = normalize_page("the \ufb01rst o\ufb00icer\u2019s \u201cpolicy\u201d \u2014 reviewed")
        self.assertIn("first", text)
        self.assertIn("officer's", text)
        self.assertIn('"policy"', text)
        self.assertGreaterEqual(counts["ligatures_expanded"], 2)

    def test_running_heads_are_stripped_only_with_enough_pages(self):
        pages = ["HEADER\nbody one\nPage 1", "HEADER\nbody two\nPage 2",
                 "HEADER\nbody three\nPage 3", "HEADER\nbody four\nPage 4"]
        cleaned, removed = strip_running_heads(pages)
        self.assertEqual(removed, 4)
        self.assertFalse(any("HEADER" in page for page in cleaned))

        few = pages[:2]
        self.assertEqual(strip_running_heads(few), (few, 0))


class TestQualityGate(unittest.TestCase):
    def test_sparse_extraction_is_unusable(self):
        quality = assess("1 2 3 4 5 6", ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(quality.verdict, "UNUSABLE")
        self.assertFalse(quality.usable)

    def test_scanned_stub_is_refused_not_scored(self):
        with self.assertRaises(UnusableDocument) as ctx:
            ingest_path(FIX / "policy_scanned_stub.pdf")
        self.assertIn("UNUSABLE", str(ctx.exception))
        self.assertIsInstance(ctx.exception.document, SourceDocument)

    def test_force_proceeds_knowingly(self):
        document = ingest_path(FIX / "policy_scanned_stub.pdf", force=True)
        self.assertEqual(document.quality.verdict, "UNUSABLE")
        self.assertTrue(document.warnings)

    def test_healthy_document_passes(self):
        self.assertEqual(ingest_path(PDF).quality.verdict, "OK")


class TestPdfIngestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = ingest_path(PDF)

    def test_key_phrases_survive_extraction(self):
        for phrase in KEY_PHRASES:
            self.assertIn(phrase, self.document.text, phrase)

    def test_hyphenated_phrase_is_recovered(self):
        # The fixture breaks "versus" across a line, which is how a justified PDF defeats
        # a literal anti-pattern search.
        self.assertIn("delivery versus payment basis", self.document.text)
        self.assertEqual(self.document.transforms["line_break_hyphens_joined"], 1)

    def test_running_furniture_is_removed(self):
        self.assertNotIn("CONFIDENTIAL", self.document.text)
        self.assertGreater(self.document.transforms["running_heads_removed"], 0)

    def test_page_map_covers_the_text(self):
        self.assertGreater(len(self.document.pages), 1)
        self.assertEqual(self.document.pages[0].start, 0)
        for offset in (0, len(self.document.text) // 2, len(self.document.text) - 1):
            self.assertIsNotNone(self.document.page_for(offset))

    def test_locate_reports_a_page_for_a_span(self):
        start = self.document.text.find("dollar-weighted average maturity")
        located = self.document.locate(start, start + 32)
        self.assertEqual(located["text"], "dollar-weighted average maturity")
        self.assertGreaterEqual(located["page"], 1)

    def test_provenance_separates_source_from_derived(self):
        provenance = self.document.provenance()
        self.assertNotEqual(provenance["source_sha256"], provenance["text_sha256"])
        self.assertEqual(provenance["media_type"], "application/pdf")
        self.assertIn(provenance["backend"], {"pdftotext", "pypdf", "stdlib-pdf"})

    def test_backends_agree_on_the_load_bearing_phrases(self):
        for name in ("pdftotext", "pypdf", "stdlib-pdf"):
            with self.subTest(backend=name):
                try:
                    document = ingest_path(PDF, backend=name)
                except IngestError:
                    self.skipTest(f"{name} unavailable")
                for phrase in KEY_PHRASES:
                    self.assertIn(phrase, document.text, f"{name}: {phrase}")

    def test_non_pdf_bytes_are_rejected_by_the_pdf_path(self):
        with self.assertRaises(IngestError):
            ingest_bytes(b"not a pdf at all", media_type="application/pdf", backend="stdlib-pdf")


class TestIngestionIsScoreNeutral(unittest.TestCase):
    """The same policy must score the same whether it arrives as text or as a PDF."""

    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(REGISTERS)
        cls.profile = json.loads((BASE / "data" / "profiles" / "water_authority.json").read_text())
        cls.facts = json.loads((FIX / "facts_water_authority.json").read_text())

    def _review(self, document_text):
        return review(self.rs, self.profile, self.facts, document_text, KeywordExtractor())

    def test_pdf_and_text_produce_the_same_verdicts(self):
        text_result = self._review(ingest_path(TXT).text)
        pdf_result = self._review(ingest_path(PDF).text)
        self.assertEqual(text_result.sections(), pdf_result.sections())
        text_verdicts = {f.control_id: f.verdict for f in text_result.findings}
        pdf_verdicts = {f.control_id: f.verdict for f in pdf_result.findings}
        self.assertEqual(text_verdicts, pdf_verdicts)

    def test_ledger_carries_provenance_and_page_numbers(self):
        source = ingest_path(PDF)
        result = self._review(source.text)
        ledger = build_ledger(self.rs, result, source.text, source.source_name,
                              "keyword-baseline", source=source)
        document = ledger["document"]
        self.assertEqual(document["backend"], source.backend)
        self.assertEqual(document["source_sha256"], source.source_sha256)
        self.assertEqual(document["quality"]["verdict"], "OK")

        pages = [
            span["page"]
            for finding in ledger["findings"]
            for element in finding["elements"]
            for span in element["spans"]
            if "page" in span
        ]
        self.assertTrue(pages)
        self.assertTrue(all(page >= 1 for page in pages))


if __name__ == "__main__":
    unittest.main()


class TestQualityNeverDowngrades(unittest.TestCase):
    """A weaker later signal must not soften an earlier fatal one."""

    def test_alpha_ratio_cannot_rescue_a_sparse_document(self):
        # Sparse enough to be UNUSABLE on character count, with an alpha ratio that on its
        # own would only justify DEGRADED.
        quality = assess("1 2 3 4 5 6", ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(quality.verdict, "UNUSABLE")
        self.assertGreaterEqual(len(quality.reasons), 2)

    def test_reasons_accumulate_across_checks(self):
        quality = assess("\ufffd" * 40 + " a" * 30, ["x"] * 4)
        self.assertEqual(quality.verdict, "UNUSABLE")
        self.assertTrue(any("replacement character" in r for r in quality.reasons))


class TestPageCounting(unittest.TestCase):
    """A page count that is a multiple of the real one puts the wrong page number against
    every citation in a report. It is a quiet, plausible-looking error, so it is pinned."""

    @classmethod
    def setUpClass(cls):
        from pfia.ingest.backends.stdlib_pdf import declared_page_count

        cls.declared = declared_page_count(PDF.read_bytes())
        cls.count = declared_page_count

    def test_the_document_declares_its_page_count(self):
        self.assertIsNotNone(self.declared)
        self.assertGreater(self.declared, 1)

    def test_every_backend_matches_the_declared_count(self):
        for name in ("pdftotext", "pypdf", "stdlib-pdf"):
            with self.subTest(backend=name):
                try:
                    document = ingest_path(PDF, backend=name)
                except IngestError:
                    self.skipTest(f"{name} unavailable")
                self.assertEqual(len(document.pages), self.declared)

    def test_fixture_has_a_page_split_across_two_content_streams(self):
        """The shape that broke stream enumeration. If this fixture loses its split page,
        the regression it guards goes untested."""
        raw = PDF.read_bytes()
        self.assertIn(b"/Contents [", raw)

    def test_mismatch_is_warned_about_not_swallowed(self):
        from pfia.ingest.loader import ingest_bytes

        # A page tree declaring more pages than there are page objects.
        broken = PDF.read_bytes().replace(b"/Count 5", b"/Count 9", 1)
        document = ingest_bytes(broken, source_name="broken.pdf",
                                media_type="application/pdf", backend="stdlib-pdf")
        self.assertTrue(any("page count mismatch" in w for w in document.warnings))


class TestUndecodedStreams(unittest.TestCase):
    """Missing text produces confident findings of absence, which is worse than a crash."""

    def test_skipped_streams_degrade_the_document(self):
        # The threshold is proportional: one undecoded stream in ten pages is a gap, one
        # in four is a quarter of the document and stops the review.
        quality = assess("word " * 10000, ["word " * 1000] * 10, skipped_streams=1)
        self.assertEqual(quality.verdict, "DEGRADED")
        self.assertEqual(quality.skipped_streams, 1)
        self.assertTrue(any("absent from this review" in r for r in quality.reasons))

    def test_many_skipped_streams_make_it_unusable(self):
        quality = assess("word " * 10000, ["word " * 1000] * 10, skipped_streams=3)
        self.assertEqual(quality.verdict, "UNUSABLE")

    def test_clean_extraction_is_unaffected(self):
        self.assertEqual(assess("word " * 4000, ["word " * 1000] * 4, 0).verdict, "OK")

    def test_quality_reaches_the_provenance(self):
        document = ingest_path(PDF)
        provenance = document.provenance()
        self.assertIn("skipped_streams", provenance["quality"])
