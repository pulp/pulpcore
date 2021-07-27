from django.db import models
from django_lifecycle import LifecycleModel


class RoleHistory(LifecycleModel):
    """Model for store Role definitions from the last time Pulp migrations were run.

    Fields:
        role_obj_classpath (models.CharField): The full classpath to the object, e.g.
            `pulpcore.app.roles.TaskAdminRole`. This is formed from the TheRole.__module__ joined
            with TheRole.__name__ using a period.
        permissions_list (models.JSONField): The list of alphabetically sorted permissions names as
            string. The alphabetical requirement is important so that arbitrary ordering of roles is
            not significant.
    """

    role_obj_classpath = models.CharField(max_length=128, null=False)
    permissions = models.JSONField(null=False)

    def __repr__(self):
        return f"RoleHistory '{self.role_obj_classpath}': {self.permissions}"
