"""Document ingestion.

Downstream code sees one string. This package is responsible for the fact that the string
is a faithful, traceable rendering of what the client actually signed.
"""

from .backends import IngestError
from .document import PageSpan, Quality, SourceDocument
from .loader import UnusableDocument, ingest_bytes, ingest_path

__all__ = [
    "IngestError", "UnusableDocument", "PageSpan", "Quality", "SourceDocument",
    "ingest_bytes", "ingest_path",
]
