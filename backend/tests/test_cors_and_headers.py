"""CORS allowlist from configuration; baseline security headers.

Requirements: FND-011, SEC-013
"""

from tests.conftest import MakeClient


def test_allowed_origin_gets_cors_headers(make_client: MakeClient) -> None:
    response = make_client().get("/api/v1/version", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_other_origin_gets_no_cors_headers(make_client: MakeClient) -> None:
    response = make_client().get("/api/v1/version", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_rejected_for_other_origin(make_client: MakeClient) -> None:
    response = make_client().options(
        "/api/v1/version",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400


def test_security_headers_present(make_client: MakeClient) -> None:
    headers = make_client().get("/health/live").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in headers
