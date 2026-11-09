"""Connection pool settings come from configuration.

Requirements: FND-008
"""

from sqlalchemy.pool import QueuePool

from app.db.session import create_db_engine
from tests.conftest import build_settings


def test_pool_uses_configured_limits() -> None:
    engine = create_db_engine(
        build_settings(
            db_pool_size=7,
            db_max_overflow=3,
            db_pool_timeout_seconds=11,
            db_pool_recycle_seconds=600,
        )
    )
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 7
    assert pool._max_overflow == 3
    assert pool._timeout == 11
    assert pool._recycle == 600
    assert pool._pre_ping is True
    engine.dispose()
