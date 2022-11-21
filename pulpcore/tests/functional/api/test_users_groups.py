import pytest
import uuid


@pytest.mark.parallel
def test_list_users(users_api_client):
    users = users_api_client.list()
    assert "admin" in [user.username for user in users.results]


@pytest.mark.parallel
def test_filter_users(users_api_client, gen_user):
    """Test that users can be filterd."""
    prefix = str(uuid.uuid4())
    users = users_api_client.list(username__contains=f"{prefix}_")
    assert len(users.results) == 0

    gen_user(username=f"{prefix}_newbee")
    gen_user(username=f"{prefix}_admin")

    users = users_api_client.list(username__contains=f"{prefix}_")
    assert len(users.results) == 2
    users = users_api_client.list(username__contains=f"{prefix}_new")
    assert len(users.results) == 1
    users = users_api_client.list(username=f"{prefix}_newbee")
    assert len(users.results) == 1


@pytest.mark.parallel
def test_crd_groups(groups_api_client, gen_object_with_cleanup):
    """Test that a group can be crd."""

    prefix = str(uuid.uuid4())
    groups = groups_api_client.list()
    assert f"{prefix}_newbees" not in [group.name for group in groups.results]
    group_href = gen_object_with_cleanup(groups_api_client, {"name": f"{prefix}_newbees"}).pulp_href
    groups = groups_api_client.list()
    assert f"{prefix}_newbees" in [group.name for group in groups.results]
    groups_api_client.delete(group_href)
    groups = groups_api_client.list()
    assert f"{prefix}_newbees" not in [group.name for group in groups.results]


@pytest.mark.parallel
def test_filter_groups(groups_api_client, gen_object_with_cleanup):
    """Test that groups can be filterd."""

    prefix = str(uuid.uuid4())
    groups = groups_api_client.list(name__contains=f"{prefix}_")
    assert len(groups.results) == 0

    gen_object_with_cleanup(groups_api_client, {"name": f"{prefix}_newbees"}).pulp_href
    gen_object_with_cleanup(groups_api_client, {"name": f"{prefix}_admins"}).pulp_href

    groups = groups_api_client.list(name__contains=f"{prefix}_")
    assert len(groups.results) == 2
    groups = groups_api_client.list(name__contains=f"{prefix}_new")
    assert len(groups.results) == 1
    groups = groups_api_client.list(name=f"{prefix}_newbees")
    assert len(groups.results) == 1
