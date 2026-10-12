"""
Regression tests: Role/Group permission replication only ran from on_*_post_save, fired when
the Role/Group row itself is saved. Permission membership changes -- .set()/.add()/.remove()/
.clear(), e.g. RoleSerializer calling role.permissions.set(...) right after creating the Role --
are an M2M change, not a save on the Role row, so post_save alone misses them. In practice:
a newly created role reached satellites with no permissions at all (the initial post_save
replicates before .permissions.set() runs), and revoking a permission never reached satellites,
leaving it live there indefinitely.
"""

import uuid

import pytest
from django.contrib.auth.models import Permission

from pulpcore.app.models import Group
from pulpcore.app.models.role import Role

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


def _replicated_permission_ids(replica, alias):
    # replica.permissions.filter(...) can't be trusted here: Permission is control-plane, so
    # that M2M manager always queries 'default' regardless of replica's own alias (see
    # rbac_sync._set_permissions_on_alias). Read the through table directly instead.
    field = type(replica)._meta.get_field("permissions")
    through = field.remote_field.through
    source_id = f"{field.m2m_field_name()}_id"
    target_id = f"{field.m2m_reverse_field_name()}_id"
    return set(
        through.objects.using(alias)
        .filter(**{source_id: replica.pk})
        .values_list(target_id, flat=True)
    )


class TestRolePermissionM2MReplication:
    def test_permissions_set_after_create_reaches_satellite(self):
        """Mirrors RoleSerializer: create the Role bare, THEN call .permissions.set() -- the
        real-world sequence that post_save alone (replicate on Role row save only) misses."""
        role = Role.objects.create(name=f"m2m-set-{uuid.uuid4()}")
        try:
            perm = Permission.objects.get(content_type__app_label="core", codename="view_task")
            role.permissions.set([perm])

            replica = Role.objects.using(SATELLITE_ALIAS).get(pulp_id=role.pulp_id)
            assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == {perm.pk}
        finally:
            role.delete()

    def test_removing_permission_reaches_satellite(self):
        """A revoked permission must stop being usable on satellites too, not just 'default'."""
        role = Role.objects.create(name=f"m2m-remove-{uuid.uuid4()}")
        try:
            perm = Permission.objects.get(content_type__app_label="core", codename="view_task")
            role.permissions.set([perm])
            replica = Role.objects.using(SATELLITE_ALIAS).get(pulp_id=role.pulp_id)
            assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == {perm.pk}

            role.permissions.remove(perm)

            assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == set()
        finally:
            role.delete()

    def test_group_permissions_clear_reaches_satellite(self):
        group = Group.objects.create(name=f"m2m-clear-{uuid.uuid4()}")
        try:
            perm = Permission.objects.get(content_type__app_label="core", codename="view_task")
            group.permissions.set([perm])
            replica = Group.objects.using(SATELLITE_ALIAS).get(pk=group.pk)
            assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == {perm.pk}

            group.permissions.clear()

            assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == set()
        finally:
            group.delete()
