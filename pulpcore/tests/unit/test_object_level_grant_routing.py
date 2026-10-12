"""
Regression test: object-level role grants (UserRole/GroupRole with content_object set) were
written and read via ambient routing instead of the target object's own database. For a
control-plane target -- Task, TaskSchedule, Domain, Group -- that's always 'default', regardless
of what domain context the request happens to be scoped to. Granting "core.task_owner" from
within satellite-domain ambient context wrote the grant to the satellite, while every read path
(ObjectRolePermissionBackend.has_perm, the add_role/remove_role/list_roles API actions, the
TaskViewSet owner-annotation optimization) looked for it on the target's own alias ('default') --
so the grant was invisible and the owner appeared to have no access to their own task.

Fixed in role_util.assign_role/remove_role (the normal path) and in every API path that writes
or reads an object-level grant directly, bypassing assign_role: RolesMixin.add_role/remove_role/
list_roles (viewsets/base.py), NestedRoleSerializer.validate (serializers/user.py),
ObjectRolePermissionBackend (backends.py), and TaskViewSet's owner-annotation query
(viewsets/task.py).
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Task
from pulpcore.app.models.role import Role, UserRole
from pulpcore.app.rbac_sync import replicate_role, replicate_user
from pulpcore.app.role_util import assign_role, remove_role
from pulpcore.constants import TASK_STATES

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

User = get_user_model()

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    domain = Domain.objects.create(
        name=f"grant-routing-{uuid.uuid4().hex[:10]}",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/grant-routing-domain"},
        database_alias=SATELLITE_ALIAS,
    )
    yield domain
    domain.delete()


class TestObjectLevelGrantFollowsTargetDb:
    def test_task_owner_grant_lands_on_default_from_satellite_context(self, satellite_domain):
        user = User.objects.create(username=str(uuid.uuid4()))
        role = Role.objects.create(name=f"task-owner-{uuid.uuid4()}")
        role.permissions.set(
            [Permission.objects.get(content_type__app_label="core", codename="view_task")]
        )
        replicate_user(user)
        replicate_role(role)
        task = Task.objects.create(name="regress-task", state=TASK_STATES.WAITING)
        try:
            # Ambient context is the satellite domain, but Task always lives in 'default' -- the
            # grant must follow the target, not ambient context.
            with with_domain(satellite_domain):
                grant = assign_role(role.name, user, task)

            assert grant._state.db == "default"
            assert UserRole.objects.using("default").filter(pk=grant.pk).exists()
            assert not UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()

            # has_perm must find it too, even checked from within the same satellite context.
            with with_domain(satellite_domain):
                assert user.has_perm("core.view_task", task)

            with with_domain(satellite_domain):
                remove_role(role.name, user, task)
            assert not UserRole.objects.using("default").filter(pk=grant.pk).exists()
        finally:
            Task.objects.using("default").filter(pk=task.pk).delete()
            role.delete()
            user.delete()
