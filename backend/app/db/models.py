"""Import every model module so Base.metadata is complete for Alembic and schema tests."""

from app.modules.settings import models as settings_models

__all__ = ["settings_models"]
