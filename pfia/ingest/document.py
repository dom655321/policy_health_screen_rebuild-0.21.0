"""The ingested document and its provenance.

Everything downstream - retrieval sweeps, model windows, verified span offsets, the
finding ledger - operates on `SourceDocument.text`. That string is derived evidence, not
the client's document, so the record of how it was derived travels with it: which backend
ran, the hash of the source bytes, the hash of the derived text, every normalization that
changed the character stream, and a page map so an offset can be reported to a board as a
page number rather than a character index.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PageSpan:
    """Half-open range of the derived text belonging to one source page."""

    page: int
    start: int
    end: int


@dataclass
class Quality:
    """Extraction quality assessment. UNUSABLE stops a review rather than scoring noise."""

    verdict: str  # OK | DEGRADED | UNUSABLE
    chars: int
    pages: int
    chars_per_page: float
    alpha_ratio: float
    empty_pages: list[int] = field(default_factory=list)
    skipped_streams: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.verdict != "UNUSABLE"


@dataclass
class SourceDocument:
    text: str
    pages: list[PageSpan] = field(default_factory=list)
    backend: str = "unknown"
    source_name: str = ""
    source_sha256: str = ""
    media_type: str = "text/plain"
    warnings: list[str] = field(default_factory=list)
    transforms: dict[str, int] = field(default_factory=dict)
    quality: Quality | None = None

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def page_for(self, offset: int) -> int | None:
        """Resolve a derived-text offset to a source page number."""
        for span in self.pages:
            if span.start <= offset < span.end:
                return span.page
        return self.pages[-1].page if self.pages and offset >= self.pages[-1].end else None

    def locate(self, start: int, end: int) -> dict[str, Any]:
        """Describe a span in terms a reader can act on."""
        first, last = self.page_for(start), self.page_for(max(start, end - 1))
        return {
            "start": start,
            "end": end,
            "page": first,
            "page_end": last if last != first else None,
            "text": self.text[start:end],
        }

    def provenance(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "media_type": self.media_type,
            "source_sha256": self.source_sha256,
            "text_sha256": self.text_sha256,
            "backend": self.backend,
            "pages": len(self.pages),
            "chars": len(self.text),
            "transforms": dict(self.transforms),
            "warnings": list(self.warnings),
            "quality": None if self.quality is None else {
                "verdict": self.quality.verdict,
                "chars_per_page": round(self.quality.chars_per_page, 1),
                "alpha_ratio": round(self.quality.alpha_ratio, 3),
                "empty_pages": list(self.quality.empty_pages),
                "skipped_streams": self.quality.skipped_streams,
                "reasons": list(self.quality.reasons),
            },
        }
