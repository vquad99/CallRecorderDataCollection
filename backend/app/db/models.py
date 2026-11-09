"""Import every model module so Base.metadata is complete for Alembic and schema tests."""

from app.modules.audit import models as audit_models
from app.modules.auth import models as auth_models
from app.modules.participants import models as participant_models
from app.modules.projects import models as project_models
from app.modules.settings import models as settings_models
from app.modules.tasks import models as task_models

__all__ = [
    "audit_models",
    "auth_models",
    "participant_models",
    "project_models",
    "settings_models",
    "task_models",
]
