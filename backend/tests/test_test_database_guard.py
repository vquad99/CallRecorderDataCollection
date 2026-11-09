"""Tests only ever run against a database named *_test.

Requirements: FND-010
"""

import pytest

from tests.conftest import assert_test_database_name


def test_guard_accepts_test_database() -> None:
    assert_test_database_name("postgresql+psycopg://u@h:5432/ccp_test")


@pytest.mark.parametrize("name", ["ccp", "ccp_dev", "production", "test_ccp"])
def test_guard_refuses_other_databases(name: str) -> None:
    with pytest.raises(RuntimeError, match="must end in _test"):
        assert_test_database_name(f"postgresql+psycopg://u@h:5432/{name}")
