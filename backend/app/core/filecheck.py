"""What is inside an uploaded document, beyond its first bytes (security audit 2026-11-23, D-160).

A file that starts like a PDF, JPEG or PNG may still carry something else: HTML after a valid
image, or a PDF that runs JavaScript or starts another program when opened. Scanned consent forms
and address proofs are opened by QC and admins and delivered to the client, so they are refused
when they hold more than a picture or a document:

- PNG: the chunks must run from the signature to IEND with nothing after it.
- JPEG: the image must end with its end marker; only zero padding may follow.
- PDF: no JavaScript, no launch, form-submit or import action, no embedded files, rich media or
  XFA forms, including inside compressed streams (read with a size limit).
"""

from __future__ import annotations

import re
import struct
import zlib

from app.core.errors import AppError

_REFUSED = (
    "This file holds more than a scanned page (for example a script or another file inside it), "
    "so it cannot be uploaded. Scan the page again, or save it again as a plain PDF or photo."
)
_DAMAGED = "This file is damaged or incomplete. Scan the page again."

# PDF names that make a document act when opened; /URI (a plain link) is allowed.
_ACTIVE_NAMES = frozenset(
    {
        b"/javascript",
        b"/js",
        b"/launch",
        b"/embeddedfile",
        b"/embeddedfiles",
        b"/richmedia",
        b"/xfa",
        b"/submitform",
        b"/importdata",
        b"/gotoe",
    }
)
_NAME = re.compile(rb"/[A-Za-z0-9#]+")
_HEX = re.compile(rb"#([0-9A-Fa-f]{2})")
_STREAM = re.compile(rb"stream\r?\n")
# Decompressing is bounded: a small file that expands without end is refused, not followed.
_MAX_STREAM_BYTES = 20 * 1024 * 1024
_MAX_TOTAL_BYTES = 60 * 1024 * 1024
_MAX_STREAMS = 2000


def _refuse(message: str = _REFUSED) -> AppError:
    return AppError(message, code="INVALID_FILE_CONTENT", status_code=422)


def _check_png(data: bytes) -> None:
    pos = 8
    while True:
        if pos + 8 > len(data):
            raise _refuse(_DAMAGED)
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise _refuse(_DAMAGED)
        pos = end
        if kind == b"IEND":
            break
    if data[pos:].strip(b"\x00"):
        raise _refuse()


def _check_jpeg(data: bytes) -> None:
    end = data.rfind(b"\xff\xd9")
    if end < 2:
        raise _refuse(_DAMAGED)
    if data[end + 2 :].strip(b"\x00"):
        raise _refuse()


def _names(chunk: bytes) -> set[bytes]:
    """PDF names in `chunk`, lowercased, with #xx escapes undone (/J#61vaScript is /JavaScript)."""
    found = set()
    for raw in _NAME.findall(chunk):
        found.add(_HEX.sub(lambda m: bytes([int(m.group(1), 16)]), raw).lower())
    return found


def _split(data: bytes) -> tuple[bytes, list[bytes]]:
    """The PDF without its stream bodies (the dictionaries, where actions are named), and the
    object streams (/Type /ObjStm: more dictionaries, compressed) decompressed within the limits.
    Other streams (page drawing, pictures) are skipped: their bytes are not names, and reading
    picture data as text would find "/JS" in it by chance."""
    outside: list[bytes] = []
    objects: list[bytes] = []
    total = 0
    pos = 0
    for count, match in enumerate(_STREAM.finditer(data)):
        if count >= _MAX_STREAMS:
            raise _refuse()
        if match.start() < pos:
            continue  # "stream" inside a body already skipped
        head = data[pos : match.start()]
        outside.append(head)
        stop = data.find(b"endstream", match.end())
        if stop < 0:
            pos = len(data)
            break
        pos = stop + len(b"endstream")
        dictionary = head[head.rfind(b"obj") :] if b"obj" in head else head[-2048:]
        if b"/objstm" not in _names(dictionary):
            continue
        engine = zlib.decompressobj()
        try:
            plain = engine.decompress(data[match.end() : stop], _MAX_STREAM_BYTES)
        except zlib.error:
            raise _refuse() from None  # an object stream that cannot be read is not accepted
        if engine.unconsumed_tail:
            raise _refuse()
        total += len(plain)
        if total > _MAX_TOTAL_BYTES:
            raise _refuse()
        objects.append(plain)
    outside.append(data[pos:])
    return b"".join(outside), objects


PADDING = bytes([0, 9, 10, 12, 13, 32])  # NUL, tab, line feed, form feed, CR, space
_MARKUP = (b"<script", b"<html", b"<iframe", b"<svg", b"<!doctype html", b"<body")


def _check_pdf(data: bytes) -> None:
    # Every complete PDF ends with %%EOF; whitespace or zero padding may follow.
    if b"%%EOF" not in data.rstrip(PADDING)[-2048:]:
        raise _refuse(_DAMAGED)
    outside, objects = _split(data)
    if any(tag in outside.lower() for tag in _MARKUP):
        raise _refuse()
    for chunk in (outside, *objects):
        if _names(chunk) & _ACTIVE_NAMES:
            raise _refuse()


def check_document(data: bytes, content_type: str) -> None:
    """422 INVALID_FILE_CONTENT when a document carries more than its picture or pages."""
    if content_type == "image/png":
        _check_png(data)
    elif content_type == "image/jpeg":
        _check_jpeg(data)
    elif content_type == "application/pdf":
        _check_pdf(data)
