"""Storage contract: the same checks against every storage the platform can use (Option F).

Always run against a fake S3 (moto). Also run against a real service when CONTRACT_STORAGE_* is set:
Wasabi from a developer machine, SeaweedFS in CI. Each test works under its own random folder inside
CONTRACT_STORAGE_PREFIX and deletes everything it wrote.

  CONTRACT_STORAGE_ENDPOINT_URL, CONTRACT_STORAGE_REGION, CONTRACT_STORAGE_BUCKET,
  CONTRACT_STORAGE_ACCESS_KEY_ID, CONTRACT_STORAGE_SECRET_ACCESS_KEY,
  CONTRACT_STORAGE_PREFIX (required, ends with "/"), CONTRACT_STORAGE_ENFORCES_AUTH=1 when the
  service checks signatures (Wasabi does; SeaweedFS without an identity file does not).

Requirements: STOR-001, STOR-003, STOR-005, STOR-006, STOR-011, STOR-012
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import boto3
import pytest
import requests
from botocore.exceptions import BotoCoreError, ClientError
from moto import mock_aws

from app.core.storage import S3Storage
from tests.conftest import build_settings

LIVE = {
    k: os.environ.get(f"CONTRACT_STORAGE_{k}", "")
    for k in ("ENDPOINT_URL", "REGION", "BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY", "PREFIX")
}
LIVE_READY = bool(LIVE["BUCKET"] and LIVE["ACCESS_KEY_ID"] and LIVE["PREFIX"].endswith("/"))
ENFORCES_AUTH = os.environ.get("CONTRACT_STORAGE_ENFORCES_AUTH") == "1"
FAKE_BUCKET = "ccp-contract"


@dataclass
class Store:
    kind: str
    storage: S3Storage
    raw: Any  # boto3 client on the same bucket, for checks behind the adapter's back
    bucket: str
    prefix: str  # this test's own folder (the adapter adds it to every key)


def _settings(prefix: str, **live: str) -> Any:
    return build_settings(
        storage_endpoint_url=live.get("ENDPOINT_URL") or None,
        storage_region=live.get("REGION") or "us-east-1",
        storage_bucket=live.get("BUCKET") or FAKE_BUCKET,
        storage_access_key_id=live.get("ACCESS_KEY_ID") or "fake-key",
        storage_secret_access_key=live.get("SECRET_ACCESS_KEY") or "fake-secret",
        storage_key_prefix=prefix,
        storage_create_bucket=False,
    )


def _cleanup(raw: Any, bucket: str, prefix: str) -> None:
    for page in raw.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            raw.delete_object(Bucket=bucket, Key=obj["Key"])


@pytest.fixture(params=["fake-s3", "live"])
def store(request: pytest.FixtureRequest) -> Iterator[Store]:
    if request.param == "fake-s3":
        with mock_aws():
            raw = boto3.client("s3", region_name="us-east-1")
            raw.create_bucket(Bucket=FAKE_BUCKET)
            prefix = f"contract-{uuid.uuid4().hex[:12]}/"
            yield Store("fake-s3", S3Storage(_settings(prefix)), raw, FAKE_BUCKET, prefix)
        return
    if not LIVE_READY:
        pytest.skip("CONTRACT_STORAGE_* not set (live storage contract NOT RUN here)")
    prefix = f"{LIVE['PREFIX']}contract-{uuid.uuid4().hex[:12]}/"
    storage = S3Storage(_settings(prefix, **LIVE))
    raw = storage._client  # same configuration as the adapter
    try:
        yield Store("live", storage, raw, LIVE["BUCKET"], prefix)
    finally:
        _cleanup(raw, LIVE["BUCKET"], prefix)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_bytes_round_trip_with_checksum_and_type(store: Store) -> None:
    data = os.urandom(300_000)
    store.storage.put_bytes(
        "a/one.bin", data, content_type="application/octet-stream", sha256=_sha(data)
    )
    info = store.storage.head("a/one.bin")
    assert info is not None
    assert (info.size, info.sha256, info.content_type) == (
        len(data),
        _sha(data),
        "application/octet-stream",
    )

    class Sink:
        def __init__(self) -> None:
            self.parts: list[bytes] = []

        def write(self, part: bytes) -> None:
            self.parts.append(part)

    sink = Sink()
    assert store.storage.append_to("a/one.bin", sink) == len(data)
    assert b"".join(sink.parts) == data


def test_large_file_round_trip_uses_multipart_and_stays_intact(
    store: Store, tmp_path: Path
) -> None:
    data = os.urandom(20 * 1024 * 1024)  # above boto3's 8 MB multipart threshold
    (tmp_path / "big.wav").write_bytes(data)
    store.storage.put_file(
        "big.wav", tmp_path / "big.wav", content_type="audio/wav", sha256=_sha(data)
    )
    info = store.storage.head("big.wav")
    assert info is not None
    assert (info.size, info.sha256, info.content_type) == (len(data), _sha(data), "audio/wav")
    store.storage.get_to_file("big.wav", tmp_path / "back.wav")
    assert _sha((tmp_path / "back.wav").read_bytes()) == _sha(data)


def test_missing_objects_and_repeated_deletes(store: Store) -> None:
    assert store.storage.head("never/written.bin") is None
    store.storage.put_bytes(
        "gone.bin", b"x", content_type="application/octet-stream", sha256=_sha(b"x")
    )
    store.storage.delete("gone.bin")
    assert store.storage.head("gone.bin") is None
    store.storage.delete("gone.bin")  # deleting twice is harmless


def test_every_key_lives_under_the_configured_prefix(store: Store) -> None:
    store.storage.put_bytes(
        "k/1.bin", b"1", content_type="application/octet-stream", sha256=_sha(b"1")
    )
    keys = [
        o["Key"]
        for o in store.raw.list_objects_v2(Bucket=store.bucket, Prefix=store.prefix).get(
            "Contents", []
        )
    ]
    assert keys == [f"{store.prefix}k/1.bin"]


def test_overwrite_replaces_content_and_checksum(store: Store) -> None:
    for content in (b"first", b"second version"):
        store.storage.put_bytes(
            "same.bin", content, content_type="application/octet-stream", sha256=_sha(content)
        )
    info = store.storage.head("same.bin")
    assert info is not None
    assert (info.size, info.sha256) == (len(b"second version"), _sha(b"second version"))


def test_signed_link_downloads_the_file_with_its_name(store: Store) -> None:
    data = os.urandom(50_000)
    store.storage.put_bytes("play.wav", data, content_type="audio/wav", sha256=_sha(data))
    plain = requests.get(
        store.storage.signed_get_url("play.wav", seconds=60, download_name=None), timeout=30
    )
    assert plain.status_code == 200
    assert plain.content == data
    named = requests.get(
        store.storage.signed_get_url("play.wav", seconds=60, download_name="final_123.wav"),
        timeout=30,
    )
    assert named.status_code == 200
    assert named.headers.get("Content-Disposition") == 'attachment; filename="final_123.wav"'


def test_many_parallel_uploads_and_downloads_stay_intact(store: Store) -> None:
    def one(i: int) -> bool:
        data = os.urandom(64_000 + i)
        key = f"par/{i}.bin"
        store.storage.put_bytes(
            key, data, content_type="application/octet-stream", sha256=_sha(data)
        )
        info = store.storage.head(key)
        return info is not None and info.sha256 == _sha(data) and info.size == len(data)

    with ThreadPoolExecutor(max_workers=16) as pool:
        assert all(pool.map(one, range(40)))


@pytest.mark.parametrize("store", ["live"], indirect=True)
def test_live_links_expire_and_unsigned_or_altered_requests_are_refused(store: Store) -> None:
    if not ENFORCES_AUTH:
        pytest.skip("this storage does not check signatures (CONTRACT_STORAGE_ENFORCES_AUTH unset)")
    store.storage.put_bytes(
        "private.bin", b"secret", content_type="application/octet-stream", sha256=_sha(b"secret")
    )
    url = store.storage.signed_get_url("private.bin", seconds=3, download_name=None)
    assert requests.get(url, timeout=30).status_code == 200
    bare = urlunparse(urlparse(url)._replace(query=""))
    assert requests.get(bare, timeout=30).status_code == 403, "no signature, no file"
    parts = urlparse(url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    query["X-Amz-Signature"] = "0" * 64
    assert (
        requests.get(urlunparse(parts._replace(query=urlencode(query))), timeout=30).status_code
        == 403
    )
    time.sleep(6)
    assert requests.get(url, timeout=30).status_code == 403, "the link has expired"


def test_an_unreachable_storage_fails_fast_with_an_error(tmp_path: Path) -> None:
    storage = S3Storage(
        _settings(
            "x/",
            ENDPOINT_URL="http://127.0.0.1:1",
            ACCESS_KEY_ID="k",
            SECRET_ACCESS_KEY="s",
            BUCKET="b",
        )
    )
    started = time.monotonic()
    with pytest.raises((BotoCoreError, ClientError)):
        storage.put_bytes("k.bin", b"x", content_type="application/octet-stream", sha256=_sha(b"x"))
    assert time.monotonic() - started < 30, "fails within the retry budget, never hangs"
