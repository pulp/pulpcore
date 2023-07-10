# Models are exposed selectively in the versioned plugin API.
# Any models defined in the pulpcore.plugin namespace should probably be proxy models.

from pulpcore.app.models.role import (  # noqa: F401
    GroupRole,
    Role,
    UserRole,
)
