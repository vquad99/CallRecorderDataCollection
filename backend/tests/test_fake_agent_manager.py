"""The stand-in's agent manager (tests/fake_txcontact.py) speaks the events of TxContact's
TxAgentManager document, so the browser journey signs a seat in the way the portal does with the
real one (D-133): a wrong password is refused, a seat gets calls only while Ready and a call puts
it On Call, TxContact's 5-minute close is followed by RECONNECT with the same session, and the
seat signs out.

Requirements: TEL-004, TEL-011, TEL-036
"""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from typing import Any

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import ClientConnection, connect

from tests import fake_txcontact

SEAT = "70001"
AUTH = {"AGENT_ID": SEAT, "TENANT_ID": "desicrew", "PASSWORD": fake_txcontact.SEAT_PASSWORD}
PLUGINS = ["PHONE", "CHAT", "BROWSER"]


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """The stand-in on a free local port, with no seats and no calls yet."""
    monkeypatch.setattr(fake_txcontact, "SEATS", {})
    monkeypatch.setattr(fake_txcontact, "CALLS", [])
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake_txcontact.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def send(ws: ClientConnection, name: str, **fields: Any) -> None:
    ws.send(json.dumps({"EVENT_NAME": name, "EVENT_CLASS": "AGENT", **fields}))


def answer(ws: ClientConnection) -> dict[str, Any]:
    event: dict[str, Any] = json.loads(ws.recv(timeout=5))
    return event


def sign_in(ws: ClientConnection) -> str:
    send(ws, "CONNECT", PLUGINS=PLUGINS, AUTH=AUTH)
    connected = answer(ws)
    assert connected["EVENT_NAME"] == "CONNECTED"
    session: str = connected["SESSION_ID"]
    send(ws, "LOGIN", SESSION_ID=session, DATA={"EXTENSION": SEAT})
    assert answer(ws)["DATA"]["STATE"] == "ONBREAK"
    return session


def get(host: str, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection(host, timeout=5)
    try:
        conn.request("GET", path)
        reply = conn.getresponse()
        return reply.status, reply.read()
    finally:
        conn.close()


def dial(host: str) -> bytes:
    query = (
        f"username={fake_txcontact.DIALER_USER}&password={fake_txcontact.DIALER_PASSWORD}"
        f"&cmp-ref=dc-new-call&phone=9876543210&preferred-agent={SEAT}&source=webapi"
    )
    return get(host, f"/txdialer/api/contact/add?{query}")[1]


def test_a_wrong_password_is_an_alert_then_the_connection_ends(host: str) -> None:
    with connect(f"ws://{host}/txagentmanager/") as ws:
        send(ws, "CONNECT", PLUGINS=PLUGINS, AUTH={**AUTH, "PASSWORD": "not-the-password"})
        alert, gone = answer(ws), answer(ws)
        assert alert["EVENT_NAME"] == "ALERT"
        assert alert["DATA"]["MESSAGE"] == "Invalid agent credentials"
        assert gone["EVENT_NAME"] == "DISCONNECTED"
        with pytest.raises(ConnectionClosed):
            ws.recv(timeout=5)
    assert get(host, f"/txagentmanager/agents/{SEAT}")[0] == 404


def test_a_seat_gets_calls_only_while_ready_and_a_call_puts_it_on_call(host: str) -> None:
    with connect(f"ws://{host}/txagentmanager/") as ws:
        session = sign_in(ws)
        assert dial(host) == b"", "On Break: the call is refused"
        send(ws, "CHANGE_AGENT_STATE", SESSION_ID=session, DATA={"STATE": "READY_FOR_CALL"})
        ready = answer(ws)
        assert (ready["EVENT_NAME"], ready["SESSION_ID"]) == ("AGENT_STATE_CHANGED", session)
        assert ready["DATA"] == {
            **ready["DATA"],
            "AGENT_ID": SEAT,
            "TENANT_ID": "desicrew",
            "STATE": "READY_FOR_CALL",
            "STATE_DESC": "Ready For Call",
        }
        assert dial(host), "Ready: the call is placed"
        assert answer(ws)["DATA"]["STATE"] == "ON_CALL"
        assert dial(host) == b"", "one call at a time"
        send(ws, "CHANGE_AGENT_STATE", SESSION_ID=session, DATA={"STATE": "READY_FOR_CALL"})
        assert answer(ws)["DATA"]["STATE"] == "READY_FOR_CALL"

        send(ws, "LOGOUT", SESSION_ID=session, DATA={"EXTENSION": SEAT})
        assert answer(ws)["DATA"]["STATE"] == "OFFLINE"
        status, body = get(host, f"/txagentmanager/agents/{SEAT}")
        assert (status, json.loads(body)["logged_in"]) == (200, False)
        send(ws, "DISCONNECT", SESSION_ID=session, DATA={})
        assert answer(ws)["EVENT_NAME"] == "DISCONNECTED"
        with pytest.raises(ConnectionClosed):
            ws.recv(timeout=5)


def test_after_the_servers_close_reconnect_keeps_the_session_and_its_state(
    host: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fake_txcontact, "CLOSE_AFTER_SECONDS", 1.0)
    with connect(f"ws://{host}/txagentmanager/") as ws:
        session = sign_in(ws)
        send(ws, "CHANGE_AGENT_STATE", SESSION_ID=session, DATA={"STATE": "READY_FOR_CALL"})
        answer(ws)
        with pytest.raises(ConnectionClosed):
            ws.recv(timeout=5)  # TxContact closes the connection after its time
    monkeypatch.setattr(fake_txcontact, "CLOSE_AFTER_SECONDS", 30.0)
    with connect(f"ws://{host}/txagentmanager/") as ws:
        send(ws, "RECONNECT", SESSION_ID="another-session", PLUGINS=PLUGINS, AUTH=AUTH)
        assert [answer(ws)["EVENT_NAME"], answer(ws)["EVENT_NAME"]] == ["ALERT", "DISCONNECTED"]
    with connect(f"ws://{host}/txagentmanager/") as ws:
        send(ws, "RECONNECT", SESSION_ID=session, PLUGINS=PLUGINS, AUTH=AUTH)
        assert answer(ws) == {"EVENT_NAME": "CONNECTED", "SESSION_ID": session, "DATA": {}}
        _, body = get(host, f"/txagentmanager/agents/{SEAT}")
        assert json.loads(body) == {
            "state": "READY_FOR_CALL",
            "logged_in": True,
            "extension": SEAT,
            "connected": True,
        }
        # An event for a session that is not this connection's is refused.
        send(ws, "LOGOUT", SESSION_ID="not-mine", DATA={"EXTENSION": SEAT})
        assert answer(ws)["DATA"]["MESSAGE"] == "Invalid session"
