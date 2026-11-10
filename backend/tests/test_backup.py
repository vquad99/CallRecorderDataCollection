"""Database backups in file storage (owner's list, O9): stored with their SHA-256, checked on the
way back, old ones pruned with the newest always kept. The full dump-and-restore cycle runs in
the CI container job (infra/backup/*.sh).

Requirements: SEC-008, OPS-004
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from app import cli
from tests.conftest import build_settings

BUCKET = "ccp-backups"


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Any]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield build_settings(
            storage_bucket=BUCKET,
            storage_access_key_id="k",
            storage_secret_access_key="s",
            media_work_dir=str(tmp_path / "work"),
        )


def test_a_backup_goes_in_and_comes_back_byte_for_byte(settings: Any) -> None:
    dump = os.urandom(3 * 1024 * 1024)
    line = cli.run_backup_upload(settings, "ccp-test.dump", io.BytesIO(dump))
    assert line.startswith("backups/db/ccp-test.dump 3145728 bytes sha256 ")
    out = io.BytesIO()
    cli.run_backup_download(settings, "backups/db/ccp-test.dump", out)
    assert out.getvalue() == dump


def test_a_damaged_backup_is_refused_before_it_is_used(settings: Any) -> None:
    cli.run_backup_upload(settings, "ccp-test.dump", io.BytesIO(b"good dump" * 1000))
    raw = boto3.client("s3", region_name="us-east-1")
    meta = raw.head_object(Bucket=BUCKET, Key="backups/db/ccp-test.dump")["Metadata"]
    raw.put_object(
        Bucket=BUCKET, Key="backups/db/ccp-test.dump", Body=b"bad! dump" * 1000, Metadata=meta
    )
    with pytest.raises(cli.SeedRefused, match="does not match its checksum"):
        cli.run_backup_download(settings, "backups/db/ccp-test.dump", io.BytesIO())
    with pytest.raises(cli.SeedRefused, match="no backup"):
        cli.run_backup_download(settings, "backups/db/missing.dump", io.BytesIO())


def test_an_empty_backup_is_refused(settings: Any) -> None:
    with pytest.raises(cli.SeedRefused, match="empty"):
        cli.run_backup_upload(settings, "ccp-empty.dump", io.BytesIO(b""))


def test_pruning_keeps_the_newest_backup(settings: Any) -> None:
    for n in range(3):
        cli.run_backup_upload(settings, f"ccp-{n}.dump", io.BytesIO(b"x" * (n + 1)))
    assert cli.run_backup_prune(settings, keep_days=30) == [], "all are recent"
    removed = cli.run_backup_prune(settings, keep_days=0)
    assert len(removed) == 2
    from app.core.storage import build_storage

    storage = build_storage(settings)
    assert storage is not None
    left = [o.key for o in storage.list_objects(cli.BACKUP_PREFIX)]
    assert len(left) == 1, "the newest backup is never pruned"
