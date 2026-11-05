from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Group, Repository
from pulpcore.app.models.role import Role
from pulpcore.app.role_util import (
    assign_role,
    get_objects_for_group,
    get_objects_for_user,
    get_users_with_perms,
)

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=str(uuid4()),
            storage_class="pulpcore.app.models.storage.FileSystem",
            database_alias=SATELLITE_ALIAS,
        )
    yield domain


def test_builtin_roles_are_initialized_locally():
    default = Role.objects.using("default").get(name="core.task_owner")
    satellite = Role.objects.using(SATELLITE_ALIAS).get(name=default.name)
    assert default.pk != satellite.pk
    assert satellite.permissions.using(SATELLITE_ALIAS).filter(codename="view_task").exists()


def test_custom_roles_and_permission_changes_are_local(satellite_domain):
    name = str(uuid4())
    default = Role.objects.create(name=name)
    assert not Role.objects.using(SATELLITE_ALIAS).filter(name=name).exists()
    with with_domain(satellite_domain):
        satellite = Role.objects.create(name=name)
        satellite.permissions.add(Permission.objects.get(codename="view_repository"))
    assert not default.permissions.exists()
    default.delete()
    assert Role.objects.using(SATELLITE_ALIAS).filter(pk=satellite.pk).exists()


@pytest.mark.parametrize("group_grant", [False, True])
def test_local_grants_use_local_permission_ids(satellite_domain, group_grant):
    from django.contrib.contenttypes.models import ContentType

    user = get_user_model().objects.create(username=str(uuid4()))
    group = Group.objects.create(name=str(uuid4()))
    group.user_set.add(user)
    with with_domain(satellite_domain):
        repo = Repository.objects.create(name=str(uuid4()))
        ContentType.objects.using(SATELLITE_ALIAS).filter(
            app_label="core", model="repository"
        ).update(model="old_repository")
        ContentType.objects.using(SATELLITE_ALIAS).create(
            id=1_000_001, app_label="core", model="repository"
        )
        ContentType.objects.clear_cache()
        # Both the content type and permission IDs differ from default.
        permission = Permission.objects.create(
            id=1_000_000,
            codename="test_satellite_permission",
            name="Satellite permission",
            content_type=ContentType.objects.get_for_model(Repository),
        )
        role = Role.objects.create(name=str(uuid4()))
        role.permissions.add(permission)
        entity = group if group_grant else user
        assign_role(role.name, entity, repo)
        assert user.has_perm("core.test_satellite_permission", repo)
        qs = Repository.objects.filter(pk=repo.pk)
        assert list(get_objects_for_user(user, "core.test_satellite_permission", qs)) == [repo]
        if group_grant:
            assert list(get_objects_for_group(group, "core.test_satellite_permission", qs)) == [
                repo
            ]
        assert list(get_users_with_perms(repo)) == [user]
        repo.delete()
        ContentType.objects.clear_cache()
