"""Object storage adapter (STOR-012). One S3-compatible implementation serves Wasabi (cloud) and
SeaweedFS (local); nothing outside this module talks to the storage service.

Objects are private. Readers get short-lived signed URLs (STOR-005). Every object carries its
SHA-256 in metadata so integrity can be re-checked without downloading (STOR-006).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import Request

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    sha256: str | None
    content_type: str | None


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str, sha256: str) -> None: ...
    def put_file(self, key: str, path: Path, *, content_type: str, sha256: str) -> None: ...
    def get_to_file(self, key: str, path: Path) -> None: ...
    def append_to(self, key: str, handle: Any) -> int: ...
    def head(self, key: str) -> ObjectInfo | None: ...
    def signed_get_url(self, key: str, *, seconds: int, download_name: str | None) -> str: ...
    def delete(self, key: str) -> None: ...


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        assert settings.storage_access_key_id is not None  # noqa: S101 (checked by storage_configured)
        assert settings.storage_secret_access_key is not None  # noqa: S101
        local = (settings.storage_endpoint_url or "").startswith("http://")
        self._bucket = str(settings.storage_bucket)
        self._prefix = settings.storage_key_prefix
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint_url,
            region_name=settings.storage_region,
            aws_access_key_id=settings.storage_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.storage_secret_access_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if local else "virtual"},
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=10,
                read_timeout=120,
            ),
        )
        if settings.storage_create_bucket:
            self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def put_bytes(self, key: str, data: bytes, *, content_type: str, sha256: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key(key),
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": sha256},
        )

    def put_file(self, key: str, path: Path, *, content_type: str, sha256: str) -> None:
        self._client.upload_file(
            str(path),
            self._bucket,
            self._key(key),
            ExtraArgs={"ContentType": content_type, "Metadata": {"sha256": sha256}},
        )

    def get_to_file(self, key: str, path: Path) -> None:
        self._client.download_file(self._bucket, self._key(key), str(path))

    def append_to(self, key: str, handle: Any) -> int:
        body = self._client.get_object(Bucket=self._bucket, Key=self._key(key))["Body"]
        total = 0
        for part in iter(lambda: body.read(1 << 20), b""):
            handle.write(part)
            total += len(part)
        return total

    def head(self, key: str) -> ObjectInfo | None:
        try:
            meta = self._client.head_object(Bucket=self._bucket, Key=self._key(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return ObjectInfo(
            size=int(meta["ContentLength"]),
            sha256=meta.get("Metadata", {}).get("sha256"),
            content_type=meta.get("ContentType"),
        )

    def signed_get_url(self, key: str, *, seconds: int, download_name: str | None) -> str:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": self._key(key)}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        url: str = self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=seconds
        )
        return url

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=self._key(key))


def build_storage(settings: Settings) -> ObjectStorage | None:
    return S3Storage(settings) if settings.storage_configured else None


def require_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage | None = request.app.state.storage
    if storage is None:
        raise AppError(
            "File storage is not configured on this server",
            code="NOT_CONFIGURED",
            status_code=503,
        )
    return storage
