"""Versioned API root (FND-012). Every module router is mounted here under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app import __version__

api_router = APIRouter(prefix="/api/v1")


class VersionInfo(BaseModel):
    name: str
    version: str
    environment: str


@api_router.get("/version", response_model=VersionInfo, tags=["meta"])
def version(request: Request) -> VersionInfo:
    return VersionInfo(
        name="conversation-collection-platform",
        version=__version__,
        environment=request.app.state.settings.app_env,
    )
