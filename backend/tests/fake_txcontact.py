"""A stand-in for TxContact, for tests only: `python -m tests.fake_txcontact [port]`.

It answers the requests the platform makes, the way TxContact was seen or documented to
(docs/integrations/txcontact/API_NOTES.md), so the phone-call flow can be driven end to end in a
real browser without ringing anyone:

- GET  /txdialer/api/contact/add        200 + a UUID as text; wrong login: 200 + empty body;
                                        cmp-ref ...attach-call rings B into the call (D-111)
- POST /txrecord/api/v1/auth/           {"status": "OK", "auth_token": ...}; wrong login: 400
- GET  /txrecord/api/search             the calls "made" through the dialer, one page
- GET  /txrecord/download/<file>        a short 8 kHz mono WAV (two alternating tones)
- GET  /txrecord/api/v1/record/mostcallshour/   calls per hour of the day
- WebSocket /txagentmanager/            the agent manager a moderator's page signs the seat in
                                        to (D-133): the events of TxContact's TxAgentManager
                                        document, see AgentManager below
- GET  /txagentmanager/agents/<seat>    the stand-in's own view of a seat, for tests

Every dialled call is listed at once with a recording, as if it had been answered and recorded.
A number ending 0000 is listed twice (two calls that fit), one ending 9999 never gets a
recording, and one ending 8888 is refused by the dialer: the three cases a person has to handle.
A seat signed in through the agent manager gets calls only while it is Ready; a call puts it
"On Call" until the page makes it Ready again. Its clock runs TXCONTACT_CLOCK_AHEAD_MINUTES ahead
of the real time, as TxContact's does (D-131): set the same value the platform is given, and the
stand-in lists calls as TxContact would. Standard library only. Never imported by the application.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import math
import os
import struct
import sys
import threading
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

DIALER_USER, DIALER_PASSWORD = "fake_dialer", "fake-dialer-pass"
RECORD_USER, RECORD_PASSWORD = "fake_rec", "fake-rec-pass"
TOKEN = "stand-in-token"
# The agent manager's sign-in: any seat number, this tenant and this password (stand-in only).
TENANT, SEAT_PASSWORD = "desicrew", "fake-seat-pass"
IST = timezone(timedelta(hours=5, minutes=30))
# How far the times it lists run ahead of the real time (TxContact's seen 2026-11-17: 330 min).
CLOCK_AHEAD = timedelta(minutes=int(os.environ.get("TXCONTACT_CLOCK_AHEAD_MINUTES") or 0))
# TxContact's agent manager closes every connection after 5 minutes (seen in the Chirp app's log).
CLOSE_AFTER_SECONDS = float(os.environ.get("FAKE_TXCONTACT_CLOSE_SECONDS") or 300)
CALLS: list[dict[str, Any]] = []
READY = "READY_FOR_CALL"
STATE_WORDS = {READY: "Ready For Call", "ONBREAK": "On Break", "OFFLINE": "Offline"}
ON_CALL = "ON_CALL"  # the stand-in's name for a seat on a call (TxContact's own: NOT VERIFIED)
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC 6455


@dataclass
class Seat:
    """A seat signed in through the agent manager; it outlives a connection (RECONNECT)."""

    agent_id: str
    session_id: str
    extension: str = ""
    state: str = "OFFLINE"
    logged_in: bool = False
    # The open connection's way to send it an event, or None between connections.
    send: Callable[[dict[str, Any]], None] | None = None

    def change(self, state: str) -> None:
        self.state = state
        if self.send:
            self.send(
                {
                    "EVENT_NAME": "AGENT_STATE_CHANGED",
                    "SESSION_ID": self.session_id,
                    "DATA": {
                        "AGENT_ID": self.agent_id,
                        "TENANT_ID": TENANT,
                        "STATE": state,
                        "STATE_DESC": STATE_WORDS.get(state, state.replace("_", " ").title()),
                        "STATE_CHANGE_TIME": int(time.time()),
                    },
                }
            )


SEATS: dict[str, Seat] = {}  # by seat number
SEATS_LOCK = threading.Lock()


class AgentManager:
    """One WebSocket connection to the agent manager, speaking the TxAgentManager document's
    events with its upper-case keys: CONNECT -> CONNECTED (wrong tenant or password: ALERT and
    DISCONNECTED, then the connection closes); RECONNECT with the session -> CONNECTED; LOGIN
    (state On Break); CHANGE_AGENT_STATE; LOGOUT (Offline); DISCONNECT -> DISCONNECTED. Every
    state change is told with AGENT_STATE_CHANGED. It says nothing until the client speaks."""

    def __init__(self, send: Callable[[dict[str, Any]], None]) -> None:
        self.send = send
        self.seat: Seat | None = None
        self.open = True

    def alert(self, message: str, end: bool = False) -> None:
        session = self.seat.session_id if self.seat else ""
        self.send({"EVENT_NAME": "ALERT", "SESSION_ID": session, "DATA": {"MESSAGE": message}})
        if end:
            self.send({"EVENT_NAME": "DISCONNECTED", "SESSION_ID": session, "DATA": {}})
            self.open = False

    def handle(self, text: str) -> None:
        try:
            event = json.loads(text)
            name = event["EVENT_NAME"]
        except (ValueError, KeyError, TypeError):
            self.alert("Invalid message")
            return
        auth = event.get("AUTH") or {}
        data = event.get("DATA") or {}
        signed = (auth.get("TENANT_ID"), auth.get("PASSWORD")) == (TENANT, SEAT_PASSWORD)
        with SEATS_LOCK:
            if name == "CONNECT":
                agent = str(auth.get("AGENT_ID") or "")
                if not (signed and agent):
                    self.alert("Invalid agent credentials", end=True)
                    return
                self.seat = Seat(agent_id=agent, session_id=str(uuid.uuid4()), send=self.send)
                SEATS[agent] = self.seat
            elif name == "RECONNECT":
                seat = SEATS.get(str(auth.get("AGENT_ID") or ""))
                if not (signed and seat and seat.session_id == event.get("SESSION_ID")):
                    self.alert("Invalid session", end=True)
                    return
                self.seat, seat.send = seat, self.send
            elif self.seat is None or event.get("SESSION_ID") != self.seat.session_id:
                self.alert("Invalid session")
                return
            seat = self.seat
            if name in ("CONNECT", "RECONNECT"):
                self.send({"EVENT_NAME": "CONNECTED", "SESSION_ID": seat.session_id, "DATA": {}})
            elif name == "LOGIN":
                seat.logged_in, seat.extension = True, str(data.get("EXTENSION") or "")
                seat.change("ONBREAK")
            elif name == "CHANGE_AGENT_STATE":
                if not seat.logged_in:
                    self.alert("Agent is not logged in")
                else:
                    seat.change(str(data.get("STATE") or ""))
            elif name == "LOGOUT":
                seat.logged_in = False
                seat.change("OFFLINE")
            elif name == "DISCONNECT":
                self.send({"EVENT_NAME": "DISCONNECTED", "SESSION_ID": seat.session_id, "DATA": {}})
                seat.send, self.open = None, False
            else:
                self.alert(f"Unknown event {name}")

    def closed(self) -> None:
        with SEATS_LOCK:
            if self.seat and self.seat.send is self.send:
                self.seat.send = None


def dial_to_seat(agent: str) -> bool:
    """Whether a call may go to this seat: a seat signed in through the agent manager must be
    Ready, and the call puts it On Call. A seat never signed in here is not checked (the platform
    with TXCONTACT_SEAT_LOGIN off, or tests that do not sign in)."""
    with SEATS_LOCK:
        seat = SEATS.get(agent)
        if seat is None:
            return True
        if seat.state != READY:
            return False
        seat.change(ON_CALL)
        return True


def _wav(seconds: int = 12, rate: int = 8000) -> bytes:
    """Two "voices" taking turns: 220 Hz and 330 Hz, half a second of quiet between turns."""
    frames = bytearray()
    for n in range(seconds * rate):
        turn = (n // rate) % 2
        quiet = (n % rate) > rate // 2 and (n % rate) < rate // 2 + rate // 8
        value = (
            0.0 if quiet else 0.35 * math.sin(2 * math.pi * (220 if turn == 0 else 330) * n / rate)
        )
        frames += struct.pack("<h", int(value * 32767))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return out.getvalue()


AUDIO = _wav()


def row(call_id: str, phone: str, agent: str, start: datetime) -> dict[str, Any]:
    """A call that really started at `start` (India time), as the search lists it: on the
    stand-in's clock, filed under that clock's date."""
    start = start + CLOCK_AHEAD
    return {
        "sl_session_id": call_id,
        "sl_trans_id": call_id,
        "sl_from": phone,
        "sl_to": agent,
        "sl_agent_id": agent,
        "sl_start_time": start.replace(tzinfo=None).isoformat(timespec="seconds"),
        "sl_end_time": (start + timedelta(seconds=12))
        .replace(tzinfo=None)
        .isoformat(timespec="seconds"),
        "sl_start_date": start.date().isoformat(),
        "sl_rec_filename": f"rec_{call_id}",
        "sl_rec_filename_ext": "wav",
        "sl_rec_file_duration": "12",
        "sl_rec_status": "C",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return  # addresses carry the dialer password: nothing is printed

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, body: Any) -> None:
        self._send(status, json.dumps(body).encode(), "application/json")

    def _authorised(self) -> bool:
        # Basic with the record login, as TxContact signs in since 2026-11-15; or the older token.
        basic = base64.b64encode(f"{RECORD_USER}:{RECORD_PASSWORD}".encode()).decode()
        if self.headers.get("Authorization", "") in (f"Token {TOKEN}", f"Basic {basic}"):
            return True
        self._json(401, {"detail": "Invalid token."})
        return False

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        if url.path == "/txrecord/api/v1/auth/":
            if (body.get("user_id"), body.get("password")) == (RECORD_USER, RECORD_PASSWORD):
                self._json(200, {"status": "OK", "auth_token": TOKEN})
            else:
                self._json(400, {"status": "ERROR", "message": "invalid username/password"})
            return
        self._json(404, {"detail": "Not found."})

    # ------------------------------------------------------ the agent manager's WebSocket (D-133)

    def _agent_manager(self) -> None:
        """Answer the WebSocket handshake, then hand every text message to an AgentManager until
        either side closes or CLOSE_AFTER_SECONDS pass (then it closes, as TxContact does)."""
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode(), usedforsecurity=False).digest()
        ).decode()
        self.wfile.write(
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode()
        )
        self.close_connection = True
        lock = threading.Lock()

        def frame(opcode: int, payload: bytes) -> None:
            size = len(payload)
            head = bytes([0x80 | opcode])
            if size < 126:
                head += bytes([size])
            elif size < 1 << 16:
                head += bytes([126]) + struct.pack(">H", size)
            else:
                head += bytes([127]) + struct.pack(">Q", size)
            # A client already gone: its next read ends this connection.
            with lock, contextlib.suppress(OSError):
                self.wfile.write(head + payload)

        manager = AgentManager(lambda event: frame(0x1, json.dumps(event).encode()))
        deadline = time.monotonic() + CLOSE_AFTER_SECONDS
        try:
            while manager.open:
                self.connection.settimeout(max(0.05, deadline - time.monotonic()))
                head = self.rfile.read(2)
                if len(head) < 2:
                    break
                size = head[1] & 0x7F
                if size == 126:
                    size = struct.unpack(">H", self.rfile.read(2))[0]
                elif size == 127:
                    size = struct.unpack(">Q", self.rfile.read(8))[0]
                mask = self.rfile.read(4) if head[1] & 0x80 else b"\0\0\0\0"
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(self.rfile.read(size)))
                opcode = head[0] & 0x0F
                if opcode == 0x8:  # the client closes
                    break
                if opcode == 0x9:
                    frame(0xA, payload)
                elif opcode == 0x1:
                    manager.handle(payload.decode("utf-8", "replace"))
        except OSError:
            pass  # TxContact's 5-minute close (a timeout), or the client vanished
        finally:
            manager.closed()
            frame(0x8, struct.pack(">H", 1000))

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path.rstrip("/") == "/txagentmanager":
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self._agent_manager()
            else:
                self._json(426, {"detail": "WebSocket only."})
            return
        if url.path.startswith("/txagentmanager/agents/"):
            seat = SEATS.get(url.path.rsplit("/", 1)[-1])
            if seat is None:
                self._json(404, {"detail": "Not found."})
            else:
                self._json(
                    200,
                    {
                        "state": seat.state,
                        "logged_in": seat.logged_in,
                        "extension": seat.extension,
                        "connected": seat.send is not None,
                    },
                )
            return
        if url.path == "/txdialer/api/contact/add":
            login = (query.get("username"), query.get("password"))
            phone = query.get("phone", "")
            if login != (DIALER_USER, DIALER_PASSWORD) or phone.endswith("8888"):
                self._send(200, b"", "text/html; charset=utf-8")
                return
            call_id = str(uuid.uuid1())
            agent = query.get("preferred-agent", "")
            if query.get("cmp-ref", "").endswith("attach-call"):
                # Participant B rung into the call on that seat: the recording is the call's own.
                self._send(200, call_id.encode(), "text/html; charset=utf-8")
                return
            if not dial_to_seat(agent):
                self._send(200, b"", "text/html; charset=utf-8")  # as a refused request
                return
            now = datetime.now(IST)
            if not phone.endswith("9999"):
                CALLS.append(row(call_id, phone, agent, now))
            if phone.endswith("0000"):
                CALLS.append(row(str(uuid.uuid1()), phone, agent, now + timedelta(seconds=20)))
            self._send(200, call_id.encode(), "text/html; charset=utf-8")
            return
        if url.path == "/txrecord/api/search":
            if not self._authorised():
                return
            rows = [
                c
                for c in CALLS
                if c["sl_agent_id"] == query.get("sl_agent_id")
                and c["sl_start_date"] == query.get("sl_start_date")
            ]
            self._json(200, {"count": len(rows), "next": None, "previous": None, "results": rows})
            return
        if url.path.startswith("/txrecord/download/"):
            if not self._authorised():
                return
            name = url.path.rsplit("/", 1)[-1]
            if any(name == f"{c['sl_rec_filename']}.wav" for c in CALLS):
                self._send(200, AUDIO, "audio/wav")
            else:
                self._json(404, {"detail": "Not found."})
            return
        if url.path == "/txrecord/api/v1/record/mostcallshour/":
            if not self._authorised():
                return
            hours: dict[str, int] = {}
            for c in CALLS:
                hour = str(int(c["sl_start_time"][11:13]))
                hours[hour] = hours.get(hour, 0) + 1
            self._json(200, hours)
            return
        self._json(404, {"detail": "Not found."})


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"fake TxContact on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
