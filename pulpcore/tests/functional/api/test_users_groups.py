import uuid

import pytest

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
def test_user_self_service(pulpcore_bindings, gen_user):
    """Test that users can update their own user information."""
    prefix = str(uuid.uuid4())
    user = gen_user(username=f"{prefix}_newbee")
    pro_user = gen_user(username=f"{prefix}_pro")
    new_body = {
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
    }
    with user:
        user_updated = pulpcore_bindings.LoginApi.login_update(new_body)
        assert user_updated.email == new_body["email"]
        assert user_updated.first_name == new_body["first_name"]
        assert user_updated.last_name == new_body["last_name"]

        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.LoginApi.login_update({"username": pro_user.username})
        assert exc.value.status == 400
        assert "This field must be unique" in exc.value.body

        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.UsersApi.read(user.user.pulp_href)
        assert exc.value.status == 403

    user_read = pulpcore_bindings.UsersApi.read(user.user.pulp_href)
    assert user_read.email == user_updated.email
    assert user_read.first_name == user_updated.first_name
    assert user_read.last_name == user_updated.last_name

    # Try password update scenarios
    with user:
        new_password = str(uuid.uuid4())
        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.LoginApi.login_update(
                {"old_password": "wrong_password", "new_password": new_password}
            )
        assert exc.value.status == 400
        assert "Old password is incorrect." in exc.value.body

        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.LoginApi.login_update(
                {"old_password": user.password, "new_password": user.password}
            )
        assert exc.value.status == 400
        assert "New password cannot be the same as the old password." in exc.value.body

        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.LoginApi.login_update({"new_password": "1234567890"})
        assert exc.value.status == 400
        assert "Old password is required to update the password." in exc.value.body

        pulpcore_bindings.LoginApi.login_update(
            {"old_password": user.password, "new_password": new_password}
        )
        with pytest.raises(pulpcore_bindings.ApiException) as exc:
            pulpcore_bindings.LoginApi.login()
        assert exc.value.status == 401
        assert "Invalid username/password" in exc.value.body
        user.password = new_password
        with user:
            user_read = pulpcore_bindings.LoginApi.login_read()
            assert user_read.username == user.username


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


@pytest.mark.parallel
def test_group_roles_with_domain(pulpcore_bindings, gen_object_with_cleanup):
    """Test that group roles with a domain can be listed and serialized.

    Regression test for https://github.com/pulp/pulpcore/issues/7095
    """
    group = gen_object_with_cleanup(pulpcore_bindings.GroupsApi, {"name": str(uuid.uuid4())})
    default_domain = pulpcore_bindings.DomainsApi.list(name="default").results[0]
    gen_object_with_cleanup(
        pulpcore_bindings.GroupsRolesApi,
        group.pulp_href,
        {"role": "core.task_viewer", "content_object": None, "domain": default_domain.pulp_href},
    )

    roles = pulpcore_bindings.GroupsRolesApi.list(group.pulp_href)
    assert roles.count == 1
    assert roles.results[0].domain == default_domain.pulp_href
