"""Ingestion backends, selected in order of fidelity."""

from .base import IngestError, PageBackend
from .pdftotext import PdftotextBackend
from .plaintext import PlaintextBackend
from .pypdf_backend import PypdfBackend
from .stdlib_pdf import StdlibPdfBackend

# Order matters. pdftotext handles multi-column policy layouts best; pypdf is a capable
# fallback where it happens to be installed; the stdlib backend always runs but is the
# least capable and says so.
PDF_BACKENDS = (PdftotextBackend, PypdfBackend, StdlibPdfBackend)

__all__ = [
    "IngestError", "PageBackend", "PDF_BACKENDS",
    "PdftotextBackend", "PypdfBackend", "StdlibPdfBackend", "PlaintextBackend",
]
