"""Global error handling: one error body, request ID, no stack traces or echoed input.

Requirements: FND-006
"""

from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import AppError
from app.main import create_app
from tests.conftest import build_settings


class _Body(BaseModel):
    count: int


def _client() -> TestClient:
    app = create_app(build_settings())

    @app.get("/api/v1/_test/boom")
    def boom() -> None:
        raise RuntimeError("internal detail that must not leak")

    @app.get("/api/v1/_test/app-error")
    def app_error() -> None:
        raise AppError("Project is archived", code="PROJECT_ARCHIVED", status_code=409)

    @app.post("/api/v1/_test/validate")
    def validate(body: _Body) -> dict[str, int]:
        return {"count": body.count}

    return TestClient(app)


def test_unhandled_error_returns_standard_500_without_details() -> None:
    response = _client().get("/api/v1/_test/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert "internal detail" not in response.text
    assert "Traceback" not in response.text


def test_app_error_keeps_its_code_and_status() -> None:
    response = _client().get("/api/v1/_test/app-error")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROJECT_ARCHIVED"


def test_not_found_uses_standard_body() -> None:
    response = _client().get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_validation_error_does_not_echo_input() -> None:
    response = _client().post("/api/v1/_test/validate", json={"count": "secret-input-value"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["loc"] == ["body", "count"]
    assert "secret-input-value" not in response.text
