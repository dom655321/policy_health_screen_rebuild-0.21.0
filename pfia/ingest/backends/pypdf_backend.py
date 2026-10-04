"""pypdf backend, imported only if the environment already has it.

Optional by construction: the project keeps zero runtime dependencies, so this backend
reports itself unavailable rather than failing an install.
"""

from __future__ import annotations

import io

from .base import IngestError


class PypdfBackend:
    name = "pypdf"

    def available(self) -> bool:
        try:
            import pypdf  # noqa: F401
        except ImportError:
            return False
        return True

    def pages(self, data: bytes) -> list[str]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise IngestError("pypdf is not installed") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            return [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise IngestError(f"pypdf could not read the document: {exc}") from exc
