"""A stand-in for TxContact, for tests only: `python -m tests.fake_txcontact [port]`.

It answers the four requests the platform makes, the way TxContact was seen or documented to
(docs/integrations/txcontact/API_NOTES.md), so the phone-call flow can be driven end to end in a
real browser without ringing anyone:

- GET  /txdialer/api/contact/add        200 + a UUID as text; wrong login: 200 + empty body
- POST /txrecord/api/v1/auth/           {"status": "OK", "auth_token": ...}; wrong login: 400
- GET  /txrecord/api/search             the calls "made" through the dialer, one page
- GET  /txrecord/download/<file>        a short 8 kHz mono WAV (two alternating tones)
- GET  /txrecord/api/v1/record/mostcallshour/   calls per hour of the day

Every dialled call is listed at once with a recording, as if it had been answered and recorded.
A number ending 0000 is listed twice (two calls that fit), one ending 9999 never gets a
recording, and one ending 8888 is refused by the dialer: the three cases a person has to handle.
Standard library only. Never imported by the application.
"""

from __future__ import annotations

import io
import json
import math
import struct
import sys
import uuid
import wave
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

DIALER_USER, DIALER_PASSWORD = "fake_dialer", "fake-dialer-pass"
RECORD_USER, RECORD_PASSWORD = "fake_rec", "fake-rec-pass"
TOKEN = "stand-in-token"
IST = timezone(timedelta(hours=5, minutes=30))
CALLS: list[dict[str, Any]] = []


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


def _row(call_id: str, phone: str, agent: str, start: datetime) -> dict[str, Any]:
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
        if self.headers.get("Authorization", "") == f"Token {TOKEN}":
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

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/txdialer/api/contact/add":
            login = (query.get("username"), query.get("password"))
            phone = query.get("phone", "")
            if login != (DIALER_USER, DIALER_PASSWORD) or phone.endswith("8888"):
                self._send(200, b"", "text/html; charset=utf-8")
                return
            call_id = str(uuid.uuid1())
            agent = query.get("preferred-agent", "")
            now = datetime.now(IST)
            if not phone.endswith("9999"):
                CALLS.append(_row(call_id, phone, agent, now))
            if phone.endswith("0000"):
                CALLS.append(_row(str(uuid.uuid1()), phone, agent, now + timedelta(seconds=20)))
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
