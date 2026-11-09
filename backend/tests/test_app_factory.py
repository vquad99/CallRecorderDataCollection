"""Application factory and versioned API root.

Requirements: FND-002, FND-012
"""

from fastapi import FastAPI
from starlette.routing import Route

from app import __version__
from app.main import create_app
from tests.conftest import MakeClient, build_settings


def test_factory_builds_an_app_with_settings_attached() -> None:
    settings = build_settings()
    app = create_app(settings)
    assert isinstance(app, FastAPI)
    assert app.state.settings is settings


def test_version_endpoint_is_under_api_v1(make_client: MakeClient) -> None:
    response = make_client().get("/api/v1/version")
    assert response.status_code == 200
    assert response.json() == {
        "name": "conversation-collection-platform",
        "version": __version__,
        "environment": "test",
    }


def test_every_route_is_versioned_or_health() -> None:
    app = create_app(build_settings(enable_api_docs=True))
    api_paths = list(app.openapi()["paths"])
    assert "/api/v1/version" in api_paths
    assert "/health/ready" in api_paths
    other_paths = [r.path for r in app.routes if isinstance(r, Route)]
    for path in api_paths + other_paths:
        assert path.startswith(("/api/v1/", "/health/")), path


def test_docs_follow_configuration(make_client: MakeClient) -> None:
    assert make_client(enable_api_docs=True).get("/api/v1/openapi.json").status_code == 200
    assert make_client(enable_api_docs=False).get("/api/v1/openapi.json").status_code == 404
