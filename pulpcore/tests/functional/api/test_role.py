import uuid
import pytest

from pulp_smash.pulp3 import constants


def test_contains_permission_filter(roles_api_client):
    """Test contains_permission query parameter."""
    # Test single permission
    roles = roles_api_client.list(contains_permission=["core.change_task"])
    assert len(roles.results) > 0
    for role in roles.results:
        assert "core.change_task" in role.permissions

    # Test two permissions
    roles = roles_api_client.list(
        contains_permission=["core.change_task", "core.view_taskschedule"]
    )
    assert len(roles.results) > 0
    change_task_present = False
    view_taskschedule_present = False

    for role in roles.results:

        if "core.change_task" in role.permissions:
            change_task_present = True

        if "core.view_taskschedule" in role.permissions:
            view_taskschedule_present = True

        assert (
            "core.change_task" in role.permissions or "core.view_taskschedule" in role.permissions
        )

    assert change_task_present and view_taskschedule_present


@pytest.mark.parallel
def test_for_object_type_filter(roles_api_client, role_factory):
    """Test for_object_type query parameter."""

    group_href = constants.BASE_PATH + "groups/"
    prefix = str(uuid.uuid4())

    multiple = role_factory(
        name=prefix + "_multi",
        description="test_role",
        permissions=["core.add_group", "core.view_task"],
    )

    single_type = role_factory(
        name=prefix + "_single",
        description="test_role",
        permissions=[
            "core.add_group",
        ],
    )

    single_type2 = role_factory(
        name=prefix + "_single2",
        description="test_role",
        permissions=["core.add_group", "core.view_group", "core.change_group", "core.delete_group"],
    )

    empty = role_factory(
        name=prefix + "_empty",
        description="test_role",
        permissions=[],
    )

    # verify that roles with permissions for other objects aren't returned.
    roles = roles_api_client.list(for_object_type=group_href, name=multiple.name)

    assert roles.count == 0

    # verify that roles for a single object type are returned.
    roles = roles_api_client.list(for_object_type=group_href, name=single_type.name)

    assert roles.count == 1

    roles = roles_api_client.list(for_object_type=group_href, name=single_type2.name)

    assert roles.count == 1

    # verify that empty roles are not returned
    roles = roles_api_client.list(for_object_type=group_href, name=empty.name)

    assert roles.count == 0

    # check multiple roles
    roles = roles_api_client.list(for_object_type=group_href, name__startswith=prefix)

    assert roles.count == 2

    returned_roles = set()
    for role in roles.results:
        returned_roles.add(role.name)

    assert returned_roles == set([single_type.name, single_type2.name])
