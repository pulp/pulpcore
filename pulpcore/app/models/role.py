from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from pulpcore.app.models import BaseModel, Group


class Role(BaseModel):
    """
    A model for the "role" part in RBAC.

    Fields:

        name (models.TextField): Unique name of the role.
        locked (models.BooleanField): Indicator for plugin managed role.

    Relations:

        permissions (models.ManyToManyField): Permissions to be granted via this role.
    """

    name = models.TextField(db_index=True, unique=True)
    description = models.TextField(null=True)
    locked = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission)


class UserRole(BaseModel):
    """
    Join table for user to role associations with optional content object.

    Relations:

        user (models.ForeignKey): User to grant permissions to.
        role (models.ForeignKey): Role to select granted permissions from.
        content_object (GenericForeignKey): Optional object to assert permissions on.
    """

    user = models.ForeignKey(
        get_user_model(), related_name="object_roles", on_delete=models.CASCADE
    )
    role = models.ForeignKey(Role, related_name="object_users", on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.TextField(null=True)
    content_object = GenericForeignKey("content_type", "object_id", for_concrete_model=False)

    class Meta:
        unique_together = (("user", "role", "content_type", "object_id"),)
        indexes = [models.Index(fields=["content_type", "object_id"])]


class GroupRole(BaseModel):
    """
    Join table for group to role associations with optional content object.

    Relations:

        group (models.ForeignKey): Group to grant permissions to.
        role (models.ForeignKey): Role to select granted permissions from.
        content_object (GenericForeignKey): Optional object to assert permissions on.
    """

    group = models.ForeignKey(Group, related_name="object_roles", on_delete=models.CASCADE)
    role = models.ForeignKey(Role, related_name="object_groups", on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.TextField(null=True)
    content_object = GenericForeignKey("content_type", "object_id", for_concrete_model=False)

    class Meta:
        unique_together = (("group", "role", "content_type", "object_id"),)
        indexes = [models.Index(fields=["content_type", "object_id"])]
