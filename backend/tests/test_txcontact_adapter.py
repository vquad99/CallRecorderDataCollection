"""TxContact adapter against a fake HTTP layer (test-only): the dial request, the recording
sign-in and search, the download, and that no password or phone number leaks into what is kept.

Requirements: TEL-001, TEL-002, TEL-010, TEL-011, TEL-035
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.adapters.telephony import ProviderError, ProviderSession
from app.adapters.txcontact import TxContact, UnsupportedNumber, file_name, national_number
from tests.conftest import build_settings

DIAL_PASSWORD = "dial-secret-p@ss"
RECORD_PASSWORD = "record-secret-pass"
PHONE = "+919876543210"


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self._pos = 0

    def read(self, amt: int = -1) -> bytes:
        if amt is None or amt < 0:
            amt = len(self._body) - self._pos
        part = self._body[self._pos : self._pos + amt]
        self._pos += len(part)
        return part

    def close(self) -> None:
        pass


class FakeServer:
    """Answers by path; records every request."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self.routes: dict[str, list[tuple[int, bytes]]] = {}

    def answer(self, path: str, status: int, body: Any) -> None:
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.routes.setdefault(path, []).append((status, raw))

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        path = urllib.parse.urlsplit(request.full_url).path
        queue = self.routes.get(path)
        if not queue:
            raise urllib.error.URLError("no route")
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return FakeResponse(status, body)


def make(server: FakeServer, **overrides: Any) -> TxContact:
    settings = build_settings(
        txcontact_dialer_username="dsc_user",
        txcontact_dialer_password=DIAL_PASSWORD,
        txcontact_record_user="rec_user",
        txcontact_record_password=RECORD_PASSWORD,
        **overrides,
    )
    return TxContact(settings, opener=server)


def test_not_configured_is_refused() -> None:
    assert build_settings().telephony_configured is False
    with pytest.raises(ValueError, match="not configured"):
        TxContact(build_settings())


def test_only_indian_mobile_numbers_are_dialled() -> None:
    assert national_number(PHONE) == "9876543210"
    for bad in ("+14155550100", "+91123", "9876543210", "+915876543210"):
        with pytest.raises(UnsupportedNumber):
            national_number(bad)


def test_dial_sends_the_documented_request_and_keeps_no_secret() -> None:
    server = FakeServer()
    server.answer("/txdialer/api/contact/add", 200, b"Contact added 9876543210 for dsc_user")
    result = make(server).dial(PHONE, "70001")
    assert result.accepted is True
    assert result.http_status == 200
    sent = server.requests[0]
    assert sent.get_method() == "GET"
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(sent.full_url).query))
    assert query == {
        "username": "dsc_user",
        "password": DIAL_PASSWORD,
        "cmp-ref": "dc-record-call",
        "phone": "9876543210",
        "preferred-agent": "70001",
        "source": "webapi",
    }
    for secret in (DIAL_PASSWORD, "9876543210", "dsc_user"):
        assert secret not in result.response_excerpt
    assert "Contact added" in result.response_excerpt


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, {"status": "error", "message": "agent not logged in"}),
        (200, {"status": False}),
        (200, b"Invalid campaign"),
        (500, b"Server Error"),
        (401, b"Unauthorized"),
    ],
)
def test_dial_refusals_are_reported_as_refused(status: int, body: Any) -> None:
    server = FakeServer()
    server.answer("/txdialer/api/contact/add", status, body)
    result = make(server).dial(PHONE, "70001")
    assert result.accepted is False
    assert result.http_status == status


def test_unreachable_provider_is_a_provider_error_without_secrets() -> None:
    server = FakeServer()  # no routes: every request fails to connect
    with pytest.raises(ProviderError) as caught:
        make(server).dial(PHONE, "70001")
    assert DIAL_PASSWORD not in str(caught.value)


def _row(**kw: Any) -> dict[str, Any]:
    row = {
        "sl_session_id": "S1",
        "sl_trans_id": "T1",
        "sl_from": "9876543210",
        "sl_to": "70001",
        "sl_agent_id": "70001",
        "sl_start_time": "2026-11-13T10:00:00",
        "sl_end_time": "2026-11-13T10:10:00",
        "sl_rec_file_duration": "600",
        "sl_rec_filename": "call_S1",
        "sl_rec_filename_ext": "wav",
        "sl_rec_status": "C",
    }
    row.update(kw)
    return row


def test_search_signs_in_pages_through_results_and_reads_times_in_the_provider_zone() -> None:
    server = FakeServer()
    server.answer("/txrecord/api/v1/auth/", 200, {"status": True, "auth_token": "tok123"})
    server.answer("/txrecord/api/search", 200, {"count": 2, "next": "page2", "results": [_row()]})
    server.answer(
        "/txrecord/api/search",
        200,
        {"count": 2, "next": None, "results": [_row(sl_session_id="S2", sl_start_time=None)]},
    )
    found = make(server).sessions("70001", date(2026, 11, 13))
    assert [s.session_id for s in found] == ["S1", "S2"]
    # Naive provider times are read in TXCONTACT_TIMEZONE (Asia/Kolkata, UTC+05:30).
    assert found[0].start == datetime(2026, 11, 13, 4, 30, tzinfo=UTC)
    assert found[1].start is None
    auth = server.requests[0]
    assert isinstance(auth.data, bytes)
    assert json.loads(auth.data) == {"user_id": "rec_user", "password": RECORD_PASSWORD}
    search = server.requests[1]
    assert search.get_header("Authorization") == "Token tok123"
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(search.full_url).query))
    assert query == {"sl_agent_id": "70001", "sl_start_date": "2026-11-13", "page": "1"}
    assert "page=2" in server.requests[2].full_url


def test_an_expired_token_is_renewed_once() -> None:
    server = FakeServer()
    server.answer("/txrecord/api/v1/auth/", 200, {"auth_token": "old"})
    server.answer("/txrecord/api/v1/auth/", 200, {"auth_token": "new"})
    server.answer("/txrecord/api/search", 401, b"expired")
    server.answer("/txrecord/api/search", 200, {"next": None, "results": []})
    assert make(server, txcontact_auth_scheme="Bearer").sessions("70001", date.today()) == []
    headers = [r.get_header("Authorization") for r in server.requests if "search" in r.full_url]
    assert headers == ["Bearer old", "Bearer new"]


def test_a_refused_sign_in_is_reported() -> None:
    server = FakeServer()
    server.answer("/txrecord/api/v1/auth/", 400, {"detail": "invalid username/password"})
    with pytest.raises(ProviderError, match=r"refused|answered 400"):
        make(server).sessions("70001", date.today())


def _session(filename: str = "call_S1", ext: str = "wav") -> ProviderSession:
    return ProviderSession(
        session_id="S1",
        trans_id="T1",
        from_number="",
        to_number="",
        agent_id="70001",
        start=None,
        end=None,
        duration="",
        rec_filename=filename,
        rec_ext=ext,
        rec_status="",
    )


def test_download_writes_the_file_and_enforces_the_size_limit(tmp_path: Path) -> None:
    server = FakeServer()
    server.answer("/txrecord/api/v1/auth/", 200, {"auth_token": "tok"})
    server.answer("/txrecord/download/call_S1.wav", 200, b"RIFF....audio-bytes")
    provider = make(server)
    dest = tmp_path / "x.wav"
    assert provider.download(_session(), dest, 1000) == len(b"RIFF....audio-bytes")
    assert dest.read_bytes() == b"RIFF....audio-bytes"
    with pytest.raises(ProviderError, match="larger"):
        provider.download(_session(), tmp_path / "y.wav", 5)


@pytest.mark.parametrize("name", ["../etc/passwd", "a/b.wav", "..wav", "", ".hidden", "x\\y.wav"])
def test_unsafe_file_names_are_refused(name: str) -> None:
    with pytest.raises(ProviderError, match="not safe"):
        file_name(_session(name, ""))


def test_file_name_takes_the_reported_extension_only_when_missing() -> None:
    assert file_name(_session("call_S1", "wav")) == "call_S1.wav"
    assert file_name(_session("call_S1.mp3", "wav")) == "call_S1.mp3"
    assert file_name(_session("call_S1", "")) == "call_S1"


def test_secrets_are_kept_out_of_logs_by_the_settings() -> None:
    settings = build_settings(
        txcontact_dialer_username="u",
        txcontact_dialer_password=DIAL_PASSWORD,
        txcontact_record_user="r",
        txcontact_record_password=RECORD_PASSWORD,
    )
    assert DIAL_PASSWORD in settings.secret_values()
    assert RECORD_PASSWORD in settings.secret_values()


def test_the_real_answers_seen_on_2026_11_13() -> None:
    """TxContact's dialer answered 200 with a UUID when it took the request, and 200 with an empty
    body for a wrong password. Empty must count as refused, or a bad login looks like a call."""
    server = FakeServer()
    server.answer("/txdialer/api/contact/add", 200, b"fec72ece-df50-11f1-96b6-bc24110b2437")
    taken = make(server).dial(PHONE, "70001")
    assert taken.accepted is True
    assert taken.reference == "fec72ece-df50-11f1-96b6-bc24110b2437"

    server = FakeServer()
    server.answer("/txdialer/api/contact/add", 200, b"")
    refused = make(server).dial(PHONE, "70001")
    assert refused.accepted is False
    assert refused.reference is None
    assert "wrong dialer username or password" in refused.response_excerpt
