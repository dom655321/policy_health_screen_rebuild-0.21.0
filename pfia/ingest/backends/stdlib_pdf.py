"""Zero-dependency PDF text extraction.

The always-available floor. It decompresses FlateDecode content streams and reads text
from the show-text operators, which covers simply generated PDFs - the kind produced by
Word, most board packet tools and government publishing systems.

It is explicit about what it cannot do. Type0 / CID fonts with custom encodings, embedded
subset fonts without a usable ToUnicode map, and any scanned page are beyond it, and it
emits a warning naming the limitation rather than returning plausible-looking garbage.
Silent partial extraction is the dangerous outcome here: it produces a document that reads
as sparse rather than as broken, and sparse text scores as ABSENT.
"""

from __future__ import annotations

import re
import zlib

from .base import IngestError

OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj(.*?)endobj", re.S)
TRAILER_ROOT = re.compile(rb"/Root\s+(\d+)\s+\d+\s+R")
REF = re.compile(rb"(\d+)\s+\d+\s+R")
KIDS = re.compile(rb"/Kids\s*\[(.*?)\]", re.S)
CONTENTS_ARRAY = re.compile(rb"/Contents\s*\[(.*?)\]", re.S)
CONTENTS_REF = re.compile(rb"/Contents\s+(\d+)\s+\d+\s+R")
PAGE_COUNT = re.compile(rb"/Type\s*/Pages\b.*?/Count\s+(\d+)", re.S)
STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
TEXT_OPERATORS = re.compile(rb"(\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]*>)\s*(Tj|TJ|'|\")|\[(.*?)\]\s*TJ", re.S)
STRING_IN_ARRAY = re.compile(rb"\((?:[^()\\]|\\.)*\)|<[0-9A-Fa-f\s]*>")
ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
           b"(": b"(", b")": b")", b"\\": b"\\"}
OCTAL = re.compile(rb"\\([0-7]{1,3})")
LINE_MOVE = re.compile(rb"(T\*|TD|Td|TL)")
# Positioning operators with their operands. A Td/TD with zero vertical offset, or a Tm
# that keeps the baseline, moves along the same line: word processors emit these between
# kerned fragments of one word ("q" "uarter" "ly"), so they are not line breaks.
MOVE = re.compile(rb"(-?[\d.]+)\s+(-?[\d.]+)\s+(Td|TD)|(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+Tm|T\*")
FRAGMENT_TAIL = re.compile(r"(?:^|[^A-Za-z])([A-Za-z]{1,2})$")
FRAGMENT_HEAD = re.compile(r"^([a-z]{1,2})(?:[^A-Za-z]|$)")


def _unescape(raw: bytes) -> bytes:
    out = bytearray()
    index = 0
    while index < len(raw):
        char = raw[index: index + 1]
        if char == b"\\" and index + 1 < len(raw):
            nxt = raw[index + 1: index + 2]
            if nxt in ESCAPES:
                out += ESCAPES[nxt]
                index += 2
                continue
            match = OCTAL.match(raw, index)
            if match:
                out.append(int(match.group(1), 8) & 0xFF)
                index = match.end()
                continue
            if nxt in (b"\n", b"\r"):
                index += 2
                continue
            index += 1
            continue
        out += char
        index += 1
    return bytes(out)


def _decode_string(token: bytes) -> str:
    if token.startswith(b"<"):
        hex_digits = re.sub(rb"\s", b"", token[1:-1])
        if len(hex_digits) % 2:
            hex_digits += b"0"
        raw = bytes.fromhex(hex_digits.decode("ascii", "ignore"))
        if raw[:2] in (b"\xfe\xff",):
            return raw.decode("utf-16-be", "replace")
        # Hex strings without a BOM are usually CID codes with no usable mapping here.
        if any(b == 0 for b in raw[::2]) and len(raw) > 2:
            return raw.decode("utf-16-be", "replace")
        return raw.decode("latin-1", "replace")
    return _unescape(token[1:-1]).decode("latin-1", "replace")


def _gap_kind(gap: bytes, state: dict) -> str:
    """'line' for a move to a new line, 'same' for a move along the baseline, '' for none."""
    kind = ""
    for m in MOVE.finditer(gap):
        if m.group(0) == b"T*":
            kind = "line"
        elif m.group(3):
            try:
                ty = float(m.group(2))
            except ValueError:
                return "line"
            kind = "line" if abs(ty) > 0.01 else (kind or "same")
        else:
            try:
                y = float(m.group(9))
            except ValueError:
                return "line"
            prev, state["y"] = state.get("y"), y
            kind = "line" if prev is None or abs(y - prev) > 0.01 else (kind or "same")
    if not kind and LINE_MOVE.search(gap) and b"TL" not in gap:
        kind = "line"
    return kind


def _join_same_line(prev: str, nxt: str) -> str:
    """Separator between two fragments positioned on the same line.

    Kerned fragments of one word join without a space; separate words keep one. A fragment
    of one or two letters against a lower-case continuation is part of the same word.
    """
    if not prev or not nxt or prev[-1].isspace() or nxt[0].isspace():
        return ""
    if nxt[0] in ",.;:)]'\u2019%":
        return ""
    if prev[-1].isalpha() and nxt[0].islower() and (FRAGMENT_TAIL.search(prev) or FRAGMENT_HEAD.search(nxt)):
        return ""
    return " "


def _content_text(content: bytes) -> str:
    parts: list[str] = []
    position = 0
    state: dict = {}
    pending_same = False
    for match in TEXT_OPERATORS.finditer(content):
        gap = content[position: match.start()]
        kind = _gap_kind(gap, state)
        if kind == "line":
            parts.append("\n")
        pending_same = kind == "same"
        position = match.end()
        if match.group(3) is not None:
            chunk = "".join(_decode_string(t) for t in STRING_IN_ARRAY.findall(match.group(3)))
        else:
            chunk = _decode_string(match.group(1))
        if pending_same and parts:
            # Judge the fragment against the word built so far, not the last chunk, so a
            # repaired word ("transaction" + "s") does not swallow the next word.
            parts.append(_join_same_line("".join(parts[-6:]), chunk))
        parts.append(chunk)
    return "".join(parts)


class StdlibPdfBackend:
    name = "stdlib-pdf"

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.skipped_streams = 0

    def available(self) -> bool:
        return True

    def _decode_stream(self, body: bytes) -> bytes | None:
        stream = STREAM.search(body)
        if not stream:
            return None
        payload = stream.group(1)
        if b"/FlateDecode" in body:
            try:
                return zlib.decompress(payload)
            except zlib.error:
                try:
                    return zlib.decompressobj().decompress(payload)
                except zlib.error:
                    self.skipped_streams += 1
                    self.warnings.append("a content stream could not be decompressed")
                    return None
        if b"/Filter" in body:
            self.skipped_streams += 1
            self.warnings.append(
                "a content stream uses an unsupported filter and was skipped; text from that "
                "page is missing from this review"
            )
            return None
        return payload

    def _page_order(self, objects: dict[int, bytes], data: bytes) -> list[int]:
        """Page object numbers in reading order, from the page tree.

        Walking the tree matters for more than ordering. Enumerating content streams
        instead - which is what this backend used to do - miscounts every document whose
        pages carry more than one content stream, and a PDF is free to split a page's
        content across an array of streams. The symptom is a page count that is a multiple
        of the real one and a page map that is wrong for the whole document, which would put
        the wrong page number against every citation in a report.
        """
        root_match = TRAILER_ROOT.search(data)
        order: list[int] = []
        seen: set[int] = set()

        def walk(number: int, depth: int = 0) -> None:
            if number in seen or depth > 64:
                return
            seen.add(number)
            body = objects.get(number, b"")
            if b"/Type" in body and b"/Page" in body and b"/Pages" not in body:
                order.append(number)
                return
            kids = KIDS.search(body)
            if not kids:
                return
            for ref in REF.finditer(kids.group(1)):
                walk(int(ref.group(1)), depth + 1)

        if root_match:
            catalog = objects.get(int(root_match.group(1)), b"")
            pages_ref = REF.search(catalog.split(b"/Pages", 1)[1]) if b"/Pages" in catalog else None
            if pages_ref:
                walk(int(pages_ref.group(1)))

        if not order:
            # No usable page tree. Fall back to document order of Page objects, which is
            # right for almost every linearly written PDF.
            self.warnings.append(
                "the page tree could not be walked; page order was taken from object order"
            )
            order = [
                number for number, body in objects.items()
                if b"/Type" in body and b"/Page" in body and b"/Pages" not in body
            ]
        return order

    def pages(self, data: bytes) -> list[str]:
        self.warnings = []
        self.skipped_streams = 0
        if not data.startswith(b"%PDF"):
            raise IngestError("not a PDF document")
        if b"/Encrypt" in data:
            raise IngestError("the PDF is encrypted; decrypt it before ingestion")

        objects: dict[int, bytes] = {
            int(num): body for num, _gen, body in OBJECT.findall(data)
        }
        page_numbers = self._page_order(objects, data)
        if not page_numbers:
            raise IngestError("no page objects found; the file may be malformed")

        out: list[str] = []
        for page_number in page_numbers:
            body = objects.get(page_number, b"")
            refs: list[int] = []
            array = CONTENTS_ARRAY.search(body)
            if array:
                refs = [int(m.group(1)) for m in REF.finditer(array.group(1))]
            else:
                single = CONTENTS_REF.search(body)
                if single:
                    refs = [int(single.group(1))]

            chunks: list[str] = []
            for ref in refs:
                payload = self._decode_stream(objects.get(ref, b""))
                if payload is None:
                    continue
                if b"Tj" not in payload and b"TJ" not in payload:
                    continue
                chunks.append(_content_text(payload))
            # An empty string still occupies a page slot. Dropping image-only pages would
            # shift every subsequent page number by one.
            out.append("".join(chunks))

        if b"/Type0" in data or b"/Identity-H" in data:
            self.warnings.append(
                "the document uses Type0/CID fonts; the stdlib backend cannot map those glyphs "
                "reliably - prefer pdftotext for this file"
            )
        if not any(page.strip() for page in out):
            raise IngestError(
                "no decodable text content found; the PDF is likely scanned or uses an "
                "unsupported font encoding"
            )
        return out


def declared_page_count(data: bytes) -> int | None:
    """The page count the PDF declares, for cross-checking whatever a backend returns."""
    counts = [int(m.group(1)) for m in PAGE_COUNT.finditer(data)]
    return max(counts) if counts else None
