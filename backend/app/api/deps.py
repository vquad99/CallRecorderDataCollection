"""What routes take from the running app: settings, the field cipher, the email sender, file
storage and the phone provider. One place, so every router asks for them the same way."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.adapters.telephony import TelephonyProvider
from app.core.config import Settings
from app.core.email import EmailSender
from app.core.storage import ObjectStorage, require_storage
from app.modules.auth.security import FieldCipher


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_cipher(request: Request) -> FieldCipher:
    cipher: FieldCipher = request.app.state.cipher
    return cipher


def get_mailer(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


def get_provider(request: Request) -> TelephonyProvider | None:
    """The phone provider, or None when phone calls are not configured (GEN-004)."""
    provider: TelephonyProvider | None = request.app.state.telephony
    return provider


AppSettings = Annotated[Settings, Depends(get_settings)]
Cipher = Annotated[FieldCipher, Depends(get_cipher)]
Mailer = Annotated[EmailSender, Depends(get_mailer)]
Provider = Annotated[TelephonyProvider | None, Depends(get_provider)]
# 503 NOT_CONFIGURED without storage. A dependency is resolved before the body is validated: a
# route that must answer 422 for a bad body first calls `require_storage` itself instead.
Storage = Annotated[ObjectStorage, Depends(require_storage)]
