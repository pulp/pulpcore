The ``AutoAddObjPermsMixin`` now calls a ``handle_creation_hooks`` interface on the configured DRF
permission class, e.g. the default ``AccessPolicyFromDB``.
