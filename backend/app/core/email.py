"""Outgoing email (password reset and invitations).

`smtp` sends through any SMTP provider (STARTTLS). `file` writes each message as an .eml file for
development and tests only; production refuses it (Settings validation).
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger("app.email")


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
    email["Subject"] = message.subject
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
                client.starttls()
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
