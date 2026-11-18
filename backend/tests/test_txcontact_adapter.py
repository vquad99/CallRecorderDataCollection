"""TxContact adapter against a fake HTTP layer (test-only): the dial request, the recording
sign-in and search, the download, that no password or phone number leaks into what is kept,
and that TxContact's clock running ahead is corrected (D-131).

Requirements: TEL-001, TEL-002, TEL-010, TEL-011, TEL-035
"""

from __future__ import annotations

import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

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
        "cmp-ref": "dc-new-call",
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
    found = make(server, txcontact_auth_scheme="Token").sessions("70001", date(2026, 11, 13))
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
        make(server, txcontact_auth_scheme="Token").sessions("70001", date.today())


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


def test_a_download_cut_short_is_refused_not_kept(tmp_path: Path) -> None:
    """A connection closed early gives a short file without an error; the length TxContact
    announced is what catches it."""

    class Short(FakeResponse):
        headers: ClassVar[dict[str, str]] = {"Content-Length": "5000"}

    class Server(FakeServer):
        def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
            if "/download/" in request.full_url:
                return Short(200, b"RIFF....only-the-start")
            return super().__call__(request, timeout)

    server = Server()
    server.answer("/txrecord/api/v1/auth/", 200, {"auth_token": "tok"})
    with pytest.raises(ProviderError, match="cut short"):
        make(server).download(_session(), tmp_path / "x.wav", 10_000)


def test_a_connection_that_drops_mid_answer_is_a_provider_error(tmp_path: Path) -> None:
    class Dropping(FakeResponse):
        def read(self, amt: int = -1) -> bytes:
            raise ConnectionResetError("peer reset")

    class Server(FakeServer):
        def __call__(self, request: urllib.request.Request, timeout: float) -> FakeResponse:
            return Dropping(200, b"")

    with pytest.raises(ProviderError, match="cut short"):
        make(Server()).dial(PHONE, "70001")
    with pytest.raises(ProviderError, match="cut short"):
        make(Server()).sessions("70001", date(2026, 11, 13))


def test_no_answer_in_time_says_so() -> None:
    def slow(request: urllib.request.Request, timeout: float) -> FakeResponse:
        raise TimeoutError("timed out")

    settings = build_settings(
        txcontact_dialer_username="u",
        txcontact_dialer_password=DIAL_PASSWORD,
        txcontact_record_user="r",
        txcontact_record_password=RECORD_PASSWORD,
    )
    with pytest.raises(ProviderError, match="did not answer in time") as caught:
        TxContact(settings, opener=slow).dial(PHONE, "70001")
    assert DIAL_PASSWORD not in str(caught.value)


def test_one_search_answer_serves_every_call_of_a_sweep() -> None:
    server = FakeServer()
    server.answer("/txrecord/api/v1/auth/", 200, {"auth_token": "tok"})
    server.answer("/txrecord/api/search", 200, {"next": None, "results": [_row()]})
    provider = make(server)
    first = provider.sessions("70001", date(2026, 11, 13))
    second = provider.sessions("70001", date(2026, 11, 13))
    assert [s.session_id for s in first] == [s.session_id for s in second] == ["S1"]
    assert sum("search" in r.full_url for r in server.requests) == 1
    provider.sessions("70002", date(2026, 11, 13))  # another seat is asked for separately
    assert sum("search" in r.full_url for r in server.requests) == 2


def test_redirects_are_refused_so_credentials_stay_with_txcontact() -> None:
    from app.adapters.txcontact import _NoRedirect

    request = urllib.request.Request("https://amber.txcontact.com/txrecord/api/search")
    assert (
        _NoRedirect().redirect_request(
            request,
            io.BytesIO(),
            302,
            "Found",
            http.client.HTTPMessage(),
            "https://elsewhere.example/",
        )
        is None
    )


def test_provider_calls_live_only_in_the_adapter_package() -> None:
    """TA-TEL-01: nothing outside app/adapters talks to the provider or names its addresses."""
    app = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in sorted(app.rglob("*.py")):
        if "adapters" in path.relative_to(app).parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(
            mark in text for mark in ("urllib.request", "http.client", "/txdialer/", "/txrecord/")
        ):
            offenders.append(str(path.relative_to(app)))
    assert offenders == []


def test_basic_sign_in_sends_the_record_login_and_fetches_no_token() -> None:
    """TxContact, 2026-11-15 (tested that day): the recording service takes the login itself in
    a Basic Authorization header; there is no token to ask for."""
    import base64

    server = FakeServer()
    server.answer("/txrecord/api/search", 200, {"count": 0, "next": None, "results": []})
    assert make(server).sessions("80003", date(2026, 11, 15)) == []
    assert [urllib.parse.urlsplit(r.full_url).path for r in server.requests] == [
        "/txrecord/api/search"
    ]
    header = server.requests[0].get_header("Authorization")
    assert header == "Basic " + base64.b64encode(f"rec_user:{RECORD_PASSWORD}".encode()).decode()
    # A refused Basic login is not retried with a fresh token: it is reported.
    refused = FakeServer()
    refused.answer("/txrecord/api/search", 403, b"forbidden")
    with pytest.raises(ProviderError, match="refused"):
        make(refused).sessions("80003", date(2026, 11, 15))
    assert len(refused.requests) == 2


def test_attach_rings_b_through_the_attach_campaign_on_the_same_seat() -> None:
    """D-111: the same dialer request, with the attach campaign (TxContact, 2026-11-15)."""
    server = FakeServer()
    server.answer("/txdialer/api/contact/add", 200, b"6f1c2c3e-c2a1-11f1-9b6e-bc24110b2437")
    adapter = make(server)
    result = adapter.attach("+919812345678", "80003")
    assert result.accepted
    assert result.reference == "6f1c2c3e-c2a1-11f1-9b6e-bc24110b2437"
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(server.requests[0].full_url).query))
    assert (query["cmp-ref"], query["phone"], query["preferred-agent"]) == (
        "dc-attach-call",
        "9812345678",
        "80003",
    )
    adapter.dial("+919876543210", "80003")
    first = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(server.requests[1].full_url).query))
    assert first["cmp-ref"] == "dc-new-call"
    assert "9812345678" not in result.response_excerpt


def test_times_running_ahead_are_moved_back_to_the_real_time() -> None:
    """D-131, seen 2026-11-17: a call placed at 14:52:03 IST was listed as starting at
    2026-11-17T20:22:07+05:30. With TXCONTACT_CLOCK_AHEAD_MINUTES=330 every time TxContact reports
    is read as the real time; unset (0), as reported. The setting is bounded to one day."""
    server = FakeServer()
    late = _row(sl_start_time="2026-11-17T20:22:07+05:30", sl_end_time="2026-11-17T20:27:07")
    server.answer("/txrecord/api/search", 200, {"next": None, "results": [late]})
    ist = ZoneInfo("Asia/Kolkata")
    (found,) = make(server, txcontact_clock_ahead_minutes=330).sessions("70001", date(2026, 11, 17))
    assert found.start == datetime(2026, 11, 17, 14, 52, 7, tzinfo=ist)
    assert found.end == datetime(2026, 11, 17, 14, 57, 7, tzinfo=ist)  # a time without a zone too
    (as_reported,) = make(server).sessions("70001", date(2026, 11, 17))
    assert as_reported.start == datetime(2026, 11, 17, 20, 22, 7, tzinfo=ist)
    with pytest.raises(ValidationError):
        build_settings(txcontact_clock_ahead_minutes=24 * 60 + 1)
