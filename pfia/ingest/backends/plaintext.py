"""Plain text and Markdown passthrough.

Text arrives already extracted, so there is no page structure. Form feeds are honoured as
page breaks where a converter left them; otherwise the whole document is page 1.
"""

from __future__ import annotations

from .base import IngestError


class PlaintextBackend:
    name = "plaintext"

    def available(self) -> bool:
        return True

    def pages(self, data: bytes) -> list[str]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("latin-1")
            except Exception as exc:  # pragma: no cover - latin-1 does not fail in practice
                raise IngestError(f"could not decode text document: {exc}") from exc
        return text.split("\f") if "\f" in text else [text]
