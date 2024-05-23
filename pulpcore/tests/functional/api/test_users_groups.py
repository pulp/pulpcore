import pytest
import uuid
from pulpcore.client.pulpcore.exceptions import ApiException


@pytest.mark.parallel
def test_list_users(pulpcore_bindings):
    users = pulpcore_bindings.UsersApi.list()
    assert "admin" in [user.username for user in users.results]


@pytest.mark.parallel
def test_filter_users(pulpcore_bindings, gen_user):
    """Test that users can be filterd."""
    prefix = str(uuid.uuid4())
    users = pulpcore_bindings.UsersApi.list(username__contains=f"{prefix}_")
    assert len(users.results) == 0

    gen_user(username=f"{prefix}_newbee")
    gen_user(username=f"{prefix}_admin")

    users = pulpcore_bindings.UsersApi.list(username__contains=f"{prefix}_")
    assert len(users.results) == 2
    users = pulpcore_bindings.UsersApi.list(username__contains=f"{prefix}_new")
    assert len(users.results) == 1
    users = pulpcore_bindings.UsersApi.list(username=f"{prefix}_newbee")
    assert len(users.results) == 1


@pytest.mark.parallel
def test_crd_groups(pulpcore_bindings, gen_object_with_cleanup):
    """Test that a group can be crd."""

    prefix = str(uuid.uuid4())
    groups = pulpcore_bindings.GroupsApi.list()
    assert f"{prefix}_newbees" not in [group.name for group in groups.results]
    group_href = gen_object_with_cleanup(
        pulpcore_bindings.GroupsApi, {"name": f"{prefix}_newbees"}
    ).pulp_href
    groups = pulpcore_bindings.GroupsApi.list()
    assert f"{prefix}_newbees" in [group.name for group in groups.results]
    pulpcore_bindings.GroupsApi.delete(group_href)
    groups = pulpcore_bindings.GroupsApi.list()
    assert f"{prefix}_newbees" not in [group.name for group in groups.results]


@pytest.mark.parallel
def test_filter_groups(pulpcore_bindings, gen_object_with_cleanup):
    """Test that groups can be filterd."""

    prefix = str(uuid.uuid4())
    groups = pulpcore_bindings.GroupsApi.list(name__contains=f"{prefix}_")
    assert len(groups.results) == 0

    gen_object_with_cleanup(pulpcore_bindings.GroupsApi, {"name": f"{prefix}_newbees"}).pulp_href
    gen_object_with_cleanup(pulpcore_bindings.GroupsApi, {"name": f"{prefix}_admins"}).pulp_href

    groups = pulpcore_bindings.GroupsApi.list(name__contains=f"{prefix}_")
    assert len(groups.results) == 2
    groups = pulpcore_bindings.GroupsApi.list(name__contains=f"{prefix}_new")
    assert len(groups.results) == 1
    groups = pulpcore_bindings.GroupsApi.list(name=f"{prefix}_newbees")
    assert len(groups.results) == 1


@pytest.mark.parallel
def test_groups_add_bad_user(pulpcore_bindings, gen_object_with_cleanup):
    """Test that adding a nonexistent user to a group fails."""

    prefix = str(uuid.uuid4())
    group_href = gen_object_with_cleanup(
        pulpcore_bindings.GroupsApi, {"name": f"{prefix}_newbees"}
    ).pulp_href
    with pytest.raises(ApiException, match="foo"):
        pulpcore_bindings.GroupsUsersApi.create(group_href, group_user={"username": "foo"})
