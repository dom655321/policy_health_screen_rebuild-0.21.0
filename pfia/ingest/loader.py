"""Ingestion entry point: bytes in, SourceDocument out."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .backends import PDF_BACKENDS, IngestError, PlaintextBackend
from .backends.stdlib_pdf import declared_page_count
from .document import PageSpan, Quality, SourceDocument
from .normalize import normalize_page, strip_running_heads
from .quality import assess

PAGE_JOIN = "\n\n"
TEXT_SUFFIXES = {".txt", ".md", ".text"}


class UnusableDocument(IngestError):
    """Raised when extraction succeeded mechanically but produced unreadable text."""

    def __init__(self, document: SourceDocument):
        self.document = document
        reasons = "; ".join(document.quality.reasons) if document.quality else "unknown"
        super().__init__(
            f"{document.source_name}: extraction quality is UNUSABLE ({reasons}). "
            "Reviewing this document would score every control against text nobody can read. "
            "Run OCR first, or pass force=True to proceed knowingly."
        )


def _select_backend(data: bytes, name: str | None):
    if name:
        for cls in list(PDF_BACKENDS) + [PlaintextBackend]:
            if cls.name == name:
                return cls()
        raise IngestError(f"unknown ingestion backend {name!r}")
    tried: list[str] = []
    for cls in PDF_BACKENDS:
        backend = cls()
        if backend.available():
            return backend
        tried.append(cls.name)
    raise IngestError(f"no PDF backend available (tried {', '.join(tried)})")


def ingest_bytes(
    data: bytes,
    source_name: str = "document",
    media_type: str | None = None,
    backend: str | None = None,
    force: bool = False,
) -> SourceDocument:
    """Extract, normalize and assess a document."""
    is_pdf = data.startswith(b"%PDF") or (media_type == "application/pdf")
    engine = _select_backend(data, backend) if is_pdf else PlaintextBackend()

    raw_pages = engine.pages(data)
    warnings: list[str] = list(getattr(engine, "warnings", []))

    if is_pdf:
        # The document declares its own page count. A backend that disagrees has mapped the
        # text onto the wrong pages, which puts the wrong page number against every
        # citation in a report - a quiet, plausible-looking error rather than a crash.
        declared = declared_page_count(data)
        if declared is not None and declared != len(raw_pages):
            warnings.append(
                f"page count mismatch: the {engine.name} backend produced {len(raw_pages)} "
                f"page(s) but the document declares {declared}. Page numbers in this review "
                "should not be relied on; try --ingest-backend pdftotext or pypdf."
            )

    cleaned, removed = strip_running_heads(raw_pages)
    transforms: dict[str, int] = {}
    if removed:
        transforms["running_heads_removed"] = removed

    normalized: list[str] = []
    for page in cleaned:
        text, counts = normalize_page(page)
        normalized.append(text)
        for key, value in counts.items():
            transforms[key] = transforms.get(key, 0) + value

    spans: list[PageSpan] = []
    cursor = 0
    chunks: list[str] = []
    for index, page in enumerate(normalized):
        start = cursor
        chunks.append(page)
        cursor += len(page)
        spans.append(PageSpan(page=index + 1, start=start, end=cursor))
        if index < len(normalized) - 1:
            chunks.append(PAGE_JOIN)
            cursor += len(PAGE_JOIN)

    text = "".join(chunks)
    document = SourceDocument(
        text=text,
        pages=spans,
        backend=engine.name,
        source_name=source_name,
        source_sha256=hashlib.sha256(data).hexdigest(),
        media_type="application/pdf" if is_pdf else "text/plain",
        warnings=warnings,
        transforms=transforms,
        quality=assess(text, normalized, getattr(engine, "skipped_streams", 0)) if is_pdf else Quality(
            verdict="OK", chars=len(text), pages=len(spans),
            chars_per_page=float(len(text)), alpha_ratio=1.0,
        ),
    )

    if transforms.get("line_break_hyphens_joined"):
        document.warnings.append(
            f"{transforms['line_break_hyphens_joined']} line-break hyphen(s) were joined; "
            "quoted spans crossing a join will not match the source page character for character"
        )
    if document.quality and document.quality.verdict != "OK":
        document.warnings.extend(document.quality.reasons)
    if document.quality and not document.quality.usable and not force:
        raise UnusableDocument(document)
    return document


def ingest_path(path: str | Path, backend: str | None = None, force: bool = False) -> SourceDocument:
    source = Path(path)
    data = source.read_bytes()
    media = "application/pdf" if source.suffix.lower() == ".pdf" else (
        "text/plain" if source.suffix.lower() in TEXT_SUFFIXES else None
    )
    return ingest_bytes(data, source_name=source.name, media_type=media, backend=backend, force=force)
