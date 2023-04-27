import pytest
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from pulpcore.app.models import Group, Remote, Repository
from pulpcore.app.models.role import Role
from pulpcore.app.role_util import assign_role, remove_role, get_objects_for_user


User = get_user_model()


@pytest.fixture
def role1(db):
    role1 = Role.objects.create(name="role1")
    role1.permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="view_repository")
    )
    return role1


@pytest.fixture
def role2(db):
    role2 = Role.objects.create(name="role2")
    role2.permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="view_remote")
    )
    return role2


@pytest.fixture
def user(db):
    return User.objects.create(username=uuid4())


@pytest.fixture
def group(user):
    group = Group.objects.create(name=uuid4())
    group.user_set.add(user)
    return group


@pytest.fixture
def repository(db):
    return Repository.objects.create(name=uuid4())


@pytest.fixture
def repository2(db):
    return Repository.objects.create(name=uuid4())


@pytest.fixture
def remote(db):
    return Remote.objects.create(name=uuid4())


@pytest.fixture
def remote2(db):
    return Remote.objects.create(name=uuid4())


def test_user_no_role(user, remote, repository):
    assert not user.has_perm("core.view_repository")
    assert not user.has_perm("core.view_repository", repository)
    assert not user.has_perm("core.view_remote")
    assert not user.has_perm("core.view_remote", remote)
    assert user.get_all_permissions() == set()
    assert user.get_all_permissions(repository) == set()


def test_user_object_role(user, repository, role1):
    assign_role("role1", user, repository)
    assert not user.has_perm("core.view_repository")
    assert user.has_perm("core.view_repository", repository)
    assert user.get_all_permissions() == set()
    assert user.get_all_permissions(repository) == {"view_repository"}
    remove_role("role1", user, repository)


def test_user_role(user, repository, role1):
    assign_role("role1", user)
    assert user.has_perm("core.view_repository")
    assert not user.has_perm("core.view_repository", repository)
    assert user.get_all_permissions() == {"core.view_repository"}
    assert user.get_all_permissions(repository) == set()
    remove_role("role1", user)


def test_group_object_role(user, group, remote, role2):
    assign_role("role2", group, remote)
    assert not user.has_perm("core.view_remote")
    assert user.has_perm("core.view_remote", remote)
    assert user.get_all_permissions() == set()
    assert user.get_all_permissions(remote) == {"view_remote"}
    remove_role("role2", group, remote)


def test_group_role(user, group, remote, role2):
    assign_role("role2", group)
    assert user.has_perm("core.view_remote")
    assert not user.has_perm("core.view_remote", remote)
    assert user.get_all_permissions() == {"core.view_remote"}
    assert user.get_all_permissions(remote) == set()
    remove_role("role2", group)


def test_combination_role(user, group, repository, repository2, remote, remote2, role1, role2):
    assign_role("role1", user, repository)
    assign_role("role2", group)
    assert user.get_all_permissions() == {"core.view_remote"}
    assert user.get_all_permissions(repository) == {"view_repository"}
    assert user.get_all_permissions(remote) == set()
    assert set(
        get_objects_for_user(user, "core.view_repository", Repository.objects.all()).values_list(
            "pk", flat=True
        )
    ) == {repository.pk}
    assert set(
        get_objects_for_user(user, "core.view_remote", Remote.objects.all()).values_list(
            "pk", flat=True
        )
    ) == {remote.pk, remote2.pk}
    remove_role("role2", group)
    remove_role("role1", user, repository)
