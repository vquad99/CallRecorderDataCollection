"""The one interface the platform uses for phone calls (TEL-001).

The flow it serves (D-101): the platform asks the provider to ring participant A and connect them to
the moderator's agent seat; the moderator adds participant B from the provider's own agent screen;
after the moderator closes the call, the platform finds the call's recording and downloads it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol


class ProviderError(RuntimeError):
    """The provider could not be reached or answered with an error. The message is safe to show:
    it never holds a password, token or full phone number."""


@dataclass(frozen=True)
class DialResult:
    accepted: bool
    http_status: int
    # The provider's answer, shortened, with credentials and the phone number removed.
    response_excerpt: str
    # The provider's identifier for this dial request, when it gives one.
    reference: str | None = None


@dataclass(frozen=True)
class ProviderSession:
    """One call as the provider's recording service lists it."""

    session_id: str
    trans_id: str
    from_number: str
    to_number: str
    agent_id: str
    start: datetime | None
    end: datetime | None
    duration: str
    rec_filename: str
    rec_ext: str
    rec_status: str


class TelephonyProvider(Protocol):
    name: str

    def dial(self, phone_e164: str, agent_id: str) -> DialResult: ...

    def sessions(self, agent_id: str, day: date) -> list[ProviderSession]: ...

    def download(self, session: ProviderSession, dest: Path, max_bytes: int) -> int: ...
