"""A virus check of uploaded documents with ClamAV (security audit 2026-11-23, D-160).

When CLAMAV_HOST is set, each scanned consent form and address proof is sent to the ClamAV daemon
(clamd) with its INSTREAM command before it is stored; a file ClamAV names as infected is refused.
No library is needed: clamd's protocol is a few bytes over TCP.

Without CLAMAV_HOST nothing is scanned (development, and until a ClamAV service is run). With
CLAMAV_REQUIRED=true an upload is refused while the scanner cannot be reached, rather than stored
unscanned.
"""

from __future__ import annotations

import logging
import socket
import struct

from app.core.config import Settings
from app.core.errors import AppError

logger = logging.getLogger("app.virus")

CHUNK = 64 * 1024


def _instream(host: str, port: int, timeout: float, data: bytes) -> str:
    """clamd's answer for `data`: "stream: OK", "stream: <name> FOUND" or an error line."""
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.sendall(b"zINSTREAM\0")
        for start in range(0, len(data), CHUNK):
            piece = data[start : start + CHUNK]
            conn.sendall(struct.pack(">I", len(piece)) + piece)
        conn.sendall(struct.pack(">I", 0))
        reply = b""
        while not reply.endswith(b"\0"):
            more = conn.recv(4096)
            if not more:
                break
            reply += more
    return reply.rstrip(b"\0").decode("utf-8", "replace").strip()


def scan(settings: Settings, data: bytes) -> None:
    """Refuses an infected file (422 INFECTED_FILE). Does nothing when no scanner is set up."""
    host = settings.clamav_host
    if not host:
        return
    try:
        answer = _instream(host, settings.clamav_port, settings.clamav_timeout_seconds, data)
    except OSError as error:
        answer = f"unreachable: {type(error).__name__}"
    if answer.endswith("FOUND"):
        logger.warning("upload_infected", extra={"signature": answer.split(":", 1)[-1].strip()})
        raise AppError(
            "The virus check found something harmful in this file, so it was not uploaded.",
            code="INFECTED_FILE",
            status_code=422,
        )
    if answer.endswith("OK"):
        return
    logger.error("virus_scan_failed", extra={"answer": answer[:200]})
    if settings.clamav_required:
        raise AppError(
            "The virus check is not available just now, so the file was not uploaded. "
            "Try again in a few minutes.",
            code="SCANNER_UNAVAILABLE",
            status_code=503,
        )
