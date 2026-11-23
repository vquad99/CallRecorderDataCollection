"""Outgoing email (password reset and invitations).

`smtp` sends through any SMTP provider (STARTTLS). `file` writes each message as an .eml file for
development and tests only; production refuses it (Settings validation).
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger("app.email")


def one_line(text: str) -> str:
    """A name put into an email's text, on one line: line breaks in it cannot add paragraphs of
    their own to a platform email (security audit 2026-11-23, D-160)."""
    return " ".join(text.split())


class EmailSendError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


def _build(message: OutgoingEmail, sender: str) -> EmailMessage:
    email = EmailMessage()
    email["From"] = sender
    email["To"] = message.to
    # One line: a header may not hold a line break, and a subject made from a name typed by staff
    # (a project's, PROJ-11) could carry one (LF, CR, U+2028 ...). str.split() takes them all.
    email["Subject"] = " ".join(message.subject.split())
    email.set_content(message.body)
    return email


class SmtpSender:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise EmailSendError("SMTP_HOST is not configured")
        self._settings = settings

    def send(self, message: OutgoingEmail) -> None:
        s = self._settings
        host = s.smtp_host
        if host is None:
            raise EmailSendError("SMTP_HOST is not configured")
        try:
            with smtplib.SMTP(host, s.smtp_port, timeout=15) as client:
                # A verified certificate for the host, not any certificate at all.
                client.starttls(context=ssl.create_default_context())
                if s.smtp_username and s.smtp_password is not None:
                    client.login(s.smtp_username, s.smtp_password.get_secret_value())
                client.send_message(_build(message, s.email_from))
        except (OSError, smtplib.SMTPException) as exc:
            logger.error("email_send_failed", extra={"error_type": type(exc).__name__})
            raise EmailSendError("email could not be sent") from exc


class FileSender:
    def __init__(self, settings: Settings) -> None:
        self._dir = Path(settings.email_file_dir)
        self._sender = settings.email_from

    def send(self, message: OutgoingEmail) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{uuid.uuid4().hex}.eml"
        path.write_bytes(bytes(_build(message, self._sender)))
        logger.info("email_written_to_file", extra={"file": str(path)})


def build_sender(settings: Settings) -> EmailSender:
    return SmtpSender(settings) if settings.email_backend == "smtp" else FileSender(settings)
