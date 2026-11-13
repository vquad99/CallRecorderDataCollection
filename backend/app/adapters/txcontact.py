"""TxContact (Telenetix) behind the telephony interface (TEL-001, D-101).

Only what TxContact has documented is used (GEN-005; docs/integrations/txcontact/API_NOTES.md):
- Dialer, from TxContact's email of 2026-11-13: GET /txdialer/api/contact/add with username,
  password, cmp-ref, phone, preferred-agent and source in the query string. TxContact's own design
  puts the password in the address, so no request address is ever logged here.
- Recording service, from its published API description (/txrecord/swagger.json, read 2026-11-13):
  POST /txrecord/api/v1/auth/ for a token, GET /txrecord/api/search for calls,
  GET /txrecord/download/{filename} for the file.

NOT VERIFIED until tested on the account: the dialer's answer format, the Authorization header
word (TXCONTACT_AUTH_SCHEME), the time zone of reported times, what sl_from/sl_to hold, and the
recording file format.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from app.adapters.telephony import DialResult, ProviderError, ProviderSession
from app.core.config import Settings

logger = logging.getLogger("app.telephony")

MAX_SEARCH_PAGES = 20
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._@+()-]{0,250}$")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_FAILURE_WORDS = ("error", "invalid", "fail", "denied", "unauthor")


class UnsupportedNumber(ProviderError):
    """The participant's number cannot be dialled through this provider."""


class _Response(Protocol):
    status: int

    def read(self, amt: int = -1) -> bytes: ...

    def close(self) -> None: ...


Opener = Callable[[urllib.request.Request, float], _Response]


def _default_open(request: urllib.request.Request, timeout: float) -> _Response:
    try:
        # The address is built here from TXCONTACT_BASE_URL (http or https only, config.py).
        return cast(_Response, urllib.request.urlopen(request, timeout=timeout))  # noqa: S310
    except urllib.error.HTTPError as err:
        return cast(_Response, err)  # an error answer is still an answer


def national_number(phone_e164: str) -> str:
    """TxContact's example dials ten digits with no country code; only Indian numbers qualify."""
    if re.fullmatch(r"\+91[6-9]\d{9}", phone_e164):
        return phone_e164[3:]
    raise UnsupportedNumber("Only Indian mobile numbers (+91) can be called through TxContact")


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class TxContact:
    name = "TXCONTACT"

    def __init__(self, settings: Settings, opener: Opener | None = None) -> None:
        if not settings.telephony_configured:
            raise ValueError("TxContact is not configured")
        self._s = settings
        self._open = opener or _default_open
        self._token: str | None = None
        self._tz = ZoneInfo(settings.txcontact_timezone)

    # ------------------------------------------------------------------ helpers

    def _secrets(self) -> list[str]:
        values = [
            self._s.txcontact_dialer_username or "",
            self._s.txcontact_record_user or "",
        ]
        for secret in (self._s.txcontact_dialer_password, self._s.txcontact_record_password):
            if secret is not None:
                values.append(secret.get_secret_value())
        if self._token:
            values.append(self._token)
        return [v for v in values if v]

    def _scrub(self, text: str, extra: list[str]) -> str:
        for value in [*self._secrets(), *extra]:
            text = text.replace(value, "***")
            quoted = urllib.parse.quote(value, safe="")
            if quoted != value:
                text = text.replace(quoted, "***")
        return re.sub(r"\s+", " ", text).strip()[:300]

    def _call(self, request: urllib.request.Request, what: str) -> tuple[int, _Response]:
        try:
            response = self._open(request, float(self._s.txcontact_timeout_seconds))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning(
                "txcontact_unreachable", extra={"what": what, "error": type(exc).__name__}
            )
            raise ProviderError(f"TxContact could not be reached ({what})") from None
        return int(response.status), response

    def _read_json(self, request: urllib.request.Request, what: str) -> Any:
        status, response = self._call(request, what)
        try:
            body = response.read(5_000_000)
        finally:
            response.close()
        if status == 401 or status == 403:
            raise _AuthRejected
        if not 200 <= status < 300:
            raise ProviderError(f"TxContact answered {status} ({what})")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderError(f"TxContact's answer was not JSON ({what})") from None

    def _auth_header(self) -> str:
        if self._token is None:
            password = self._s.txcontact_record_password
            assert password is not None  # noqa: S101  (telephony_configured)
            payload = json.dumps(
                {"user_id": self._s.txcontact_record_user, "password": password.get_secret_value()}
            ).encode()
            request = urllib.request.Request(  # noqa: S310
                f"{self._s.txcontact_base_url}/txrecord/api/v1/auth/",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            try:
                body = self._read_json(request, "recording sign-in")
            except _AuthRejected:
                raise ProviderError("TxContact refused the recording sign-in") from None
            token = body.get("auth_token") if isinstance(body, dict) else None
            if not isinstance(token, str) or not token:
                raise ProviderError("TxContact's recording sign-in returned no token")
            self._token = token
        scheme = self._s.txcontact_auth_scheme.strip()
        return f"{scheme} {self._token}" if scheme else self._token

    def _authorised(self, url: str, what: str) -> Any:
        for attempt in (1, 2):
            request = urllib.request.Request(  # noqa: S310
                url, headers={"Authorization": self._auth_header(), "Accept": "application/json"}
            )
            try:
                return self._read_json(request, what)
            except _AuthRejected:
                self._token = None  # an expired token: sign in again once
                if attempt == 2:
                    raise ProviderError(f"TxContact refused the request ({what})") from None
        raise ProviderError(f"TxContact refused the request ({what})")

    def _time(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=self._tz)

    # ------------------------------------------------------------------ interface

    def dial(self, phone_e164: str, agent_id: str) -> DialResult:
        phone = national_number(phone_e164)
        password = self._s.txcontact_dialer_password
        assert password is not None  # noqa: S101  (telephony_configured)
        query = urllib.parse.urlencode(
            {
                "username": self._s.txcontact_dialer_username,
                "password": password.get_secret_value(),
                "cmp-ref": self._s.txcontact_campaign_ref,
                "phone": phone,
                "preferred-agent": agent_id,
                "source": self._s.txcontact_source,
            }
        )
        request = urllib.request.Request(  # noqa: S310
            f"{self._s.txcontact_base_url}/txdialer/api/contact/add?{query}", method="GET"
        )
        status, response = self._call(request, "dial")
        try:
            body = response.read(20_000)
        finally:
            response.close()
        text = body.decode("utf-8", errors="replace").strip()
        excerpt = self._scrub(text, [phone, phone_e164])
        # Tested 2026-11-13: an accepted request answers 200 with a UUID as plain text; a wrong
        # username or password answers 200 with an empty body. Empty therefore means refused.
        reference = text if _UUID.fullmatch(text) else None
        accepted = 200 <= status < 300 and bool(text) and not _says_failure(text)
        if not text and 200 <= status < 300:
            excerpt = "(empty answer: usually a wrong dialer username or password)"
        return DialResult(
            accepted=accepted, http_status=status, response_excerpt=excerpt, reference=reference
        )

    def sessions(self, agent_id: str, day: date) -> list[ProviderSession]:
        found: list[ProviderSession] = []
        for page in range(1, MAX_SEARCH_PAGES + 1):
            query = urllib.parse.urlencode(
                {"sl_agent_id": agent_id, "sl_start_date": day.isoformat(), "page": page}
            )
            body = self._authorised(
                f"{self._s.txcontact_base_url}/txrecord/api/search?{query}", "recording search"
            )
            rows = body.get("results", []) if isinstance(body, dict) else body
            if not isinstance(rows, list):
                raise ProviderError("TxContact's search answer has no list of calls")
            for row in rows:
                if isinstance(row, dict):
                    found.append(self._session(row))
            if not (isinstance(body, dict) and body.get("next")):
                break
        return found

    def _session(self, row: dict[str, Any]) -> ProviderSession:
        def text(key: str) -> str:
            value = row.get(key)
            return "" if value is None else str(value)

        return ProviderSession(
            session_id=text("sl_session_id") or text("sl_trans_id"),
            trans_id=text("sl_trans_id"),
            from_number=text("sl_from"),
            to_number=text("sl_to"),
            agent_id=text("sl_agent_id"),
            start=self._time(row.get("sl_start_time")),
            end=self._time(row.get("sl_end_time")),
            duration=text("sl_rec_file_duration"),
            rec_filename=text("sl_rec_filename"),
            rec_ext=text("sl_rec_filename_ext"),
            rec_status=text("sl_rec_status"),
        )

    def download(self, session: ProviderSession, dest: Path, max_bytes: int) -> int:
        name = file_name(session)
        url = f"{self._s.txcontact_base_url}/txrecord/download/{urllib.parse.quote(name, safe='')}"
        for attempt in (1, 2):
            request = urllib.request.Request(  # noqa: S310
                url, headers={"Authorization": self._auth_header()}
            )
            status, response = self._call(request, "recording download")
            try:
                if status in (401, 403):
                    self._token = None
                    if attempt == 2:
                        raise ProviderError("TxContact refused the recording download")
                    continue
                if not 200 <= status < 300:
                    raise ProviderError(f"TxContact answered {status} to the recording download")
                size = 0
                with dest.open("wb") as handle:
                    while part := response.read(1 << 20):
                        size += len(part)
                        if size > max_bytes:
                            raise ProviderError("The recording is larger than the allowed maximum")
                        handle.write(part)
                if size == 0:
                    raise ProviderError("TxContact sent an empty recording")
                return size
            finally:
                response.close()
        raise ProviderError("TxContact refused the recording download")


class _AuthRejected(Exception):
    pass


def _says_failure(text: str) -> bool:
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        lowered = text.lower()
        return any(word in lowered for word in _FAILURE_WORDS)
    if isinstance(body, dict):
        status = str(body.get("status", "")).strip().lower()
        if status in ("false", "error", "failed", "failure", "0") or body.get("error"):
            return True
    return False


def file_name(session: ProviderSession) -> str:
    """The file to ask for: the reported name, with the reported extension when it has none.
    Anything that could reach another path on TxContact's server is refused (TEL-035)."""
    name = session.rec_filename.strip()
    ext = session.rec_ext.strip().lstrip(".")
    if name and "." not in name and re.fullmatch(r"[A-Za-z0-9]{1,5}", ext):
        name = f"{name}.{ext}"
    if not _SAFE_FILENAME.match(name) or ".." in name:
        raise ProviderError("TxContact reported a recording file name that is not safe to use")
    return name
