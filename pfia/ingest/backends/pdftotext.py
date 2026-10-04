"""Poppler pdftotext via subprocess.

Preferred when present. It is the most faithful of the three on real-world policy PDFs,
particularly on multi-column layouts, and it costs the project nothing in dependencies
because it is an external binary rather than an import.

`-layout` is deliberate: policies carry maturity limits and concentration caps in tables,
and reflowing a table into prose order scrambles which number belongs to which fund.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import IngestError


class PdftotextBackend:
    name = "pdftotext"

    def __init__(self, layout: bool = True, timeout: int = 120):
        self.layout = layout
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which("pdftotext") is not None

    def pages(self, data: bytes) -> list[str]:
        if not self.available():
            raise IngestError("pdftotext is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.pdf"
            source.write_bytes(data)
            command = ["pdftotext", "-q", "-enc", "UTF-8"]
            if self.layout:
                command.append("-layout")
            command += [str(source), "-"]
            try:
                completed = subprocess.run(
                    command, capture_output=True, timeout=self.timeout, check=True
                )
            except subprocess.CalledProcessError as exc:
                raise IngestError(f"pdftotext failed: {exc.stderr.decode('utf-8', 'replace')[:200]}") from exc
            except subprocess.TimeoutExpired as exc:
                raise IngestError("pdftotext timed out") from exc
        text = completed.stdout.decode("utf-8", "replace")
        pages = text.split("\f")
        # pdftotext emits a trailing form feed; an empty final page would skew the
        # per-page quality metrics and the page map.
        while pages and not pages[-1].strip():
            pages.pop()
        return pages
