"""Backend protocol.

A backend turns source bytes into a list of per-page strings. Nothing else. Normalization,
page mapping and quality assessment are shared, so backends stay comparable and swapping
one cannot quietly change how the text is cleaned.
"""

from __future__ import annotations

from typing import Protocol


class IngestError(RuntimeError):
    """Raised when a backend cannot read the document at all."""


class PageBackend(Protocol):
    name: str

    def available(self) -> bool:
        """Whether this backend can run in the current environment."""
        ...

    def pages(self, data: bytes) -> list[str]:
        """Return raw extracted text, one string per source page."""
        ...
