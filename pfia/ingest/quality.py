"""Extraction quality gate.

The failure this exists to prevent: a scanned, image-only PDF extracts as near-empty text,
every control resolves ABSENT, and the pipeline emits a confident 0.00 statutory index for
a policy nobody has actually read. That report is worse than no report, because it looks
like a finding rather than a malfunction.

So a document that cannot be read is refused, not scored.
"""

from __future__ import annotations

import re

from .document import Quality

MIN_CHARS_PER_PAGE = 250
DEGRADED_CHARS_PER_PAGE = 900
MIN_ALPHA_RATIO = 0.55
MIN_TOTAL_CHARS = 1200

SEVERITY = {"OK": 0, "DEGRADED": 1, "UNUSABLE": 2}


def _worst(current: str, candidate: str) -> str:
    """Verdicts only ever get worse.

    Each check is an independent signal of the same underlying failure, so a later, weaker
    signal must never soften an earlier fatal one. Without this a scanned document that
    trips the character-count floor could be downgraded to DEGRADED by the alpha-ratio
    check and go on to be scored.
    """
    return current if SEVERITY[current] >= SEVERITY[candidate] else candidate


SPLIT_PATTERNS = (
    re.compile(r"(?<![A-Za-z'\u2019])[b-hj-zB-HJ-Z]\s[a-z]{2,}"),            # "q uarterly", "T he"
    re.compile(r"[a-z]{3,}\s(?:s|ly|ed|ing|tion|ment|ity)\b"),                # "transaction s"
)


def word_split_artifacts(text: str) -> int:
    """Count likely word fragments split by a space (a PDF kerning artifact)."""
    return sum(len(p.findall(text)) for p in SPLIT_PATTERNS)


def assess(text: str, page_texts: list[str], skipped_streams: int = 0) -> Quality:
    pages = max(1, len(page_texts))
    chars = len(text)
    per_page = chars / pages
    alpha = sum(c.isalpha() or c.isspace() for c in text)
    alpha_ratio = alpha / chars if chars else 0.0
    empty = [i + 1 for i, page in enumerate(page_texts) if len(page.strip()) < 50]

    reasons: list[str] = []
    verdict = "OK"

    if chars < MIN_TOTAL_CHARS:
        verdict = _worst(verdict, "UNUSABLE")
        reasons.append(
            f"only {chars} characters extracted; the document is probably image-only or the "
            "backend could not decode its fonts"
        )
    if per_page < MIN_CHARS_PER_PAGE:
        verdict = _worst(verdict, "UNUSABLE")
        reasons.append(f"{per_page:.0f} characters per page is below the {MIN_CHARS_PER_PAGE} floor")
    elif per_page < DEGRADED_CHARS_PER_PAGE:
        verdict = _worst(verdict, "DEGRADED")
        reasons.append(f"{per_page:.0f} characters per page is sparse for a policy document")

    if alpha_ratio < MIN_ALPHA_RATIO:
        verdict = _worst(verdict, "UNUSABLE" if alpha_ratio < 0.35 else "DEGRADED")
        reasons.append(
            f"alphabetic ratio {alpha_ratio:.2f} suggests glyph mapping failure rather than prose"
        )
    if "\ufffd" in text:
        verdict = _worst(verdict, "DEGRADED")
        reasons.append(f"{text.count(chr(0xFFFD))} replacement character(s) in the derived text")

    if skipped_streams:
        # A skipped stream is missing text, and missing text produces confident
        # not-found findings against sections the reviewer can see on the page. That is
        # the most misleading failure this pipeline can produce, so it degrades the
        # document rather than emitting a warning nobody reads.
        verdict = _worst(verdict, "UNUSABLE" if skipped_streams > pages * 0.2 else "DEGRADED")
        reasons.append(
            f"{skipped_streams} content stream(s) could not be decoded and their text is "
            "absent from this review; any not-found finding may be an extraction gap "
            "rather than a policy gap. Try --ingest-backend pdftotext or pypdf."
        )

    splits = word_split_artifacts(text)
    words = max(1, len(re.findall(r"[A-Za-z]{2,}", text)))
    if splits >= 5 and splits / words > 0.004:
        # "q uarter ly", "transaction s": kerned fragments read as separate words. Term
        # matching then misses whole instruments, which reads as "not authorized".
        verdict = _worst(verdict, "DEGRADED")
        reasons.append(
            f"{splits} word-splitting artifact(s) (for example a word broken into fragments); "
            "instrument and requirement matching may miss text. Install pypdf "
            "(pip install pypdf) or poppler (brew install poppler) and re-run."
        )

    if len(empty) > pages * 0.25:
        verdict = _worst(verdict, "DEGRADED")
        reasons.append(f"{len(empty)} of {pages} pages produced almost no text: {empty[:10]}")

    return Quality(
        skipped_streams=skipped_streams,
        verdict=verdict,
        chars=chars,
        pages=pages,
        chars_per_page=per_page,
        alpha_ratio=alpha_ratio,
        empty_pages=empty,
        reasons=reasons,
    )
