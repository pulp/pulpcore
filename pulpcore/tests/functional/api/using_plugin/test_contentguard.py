from aiohttp import BasicAuth
from base64 import b64encode
import json
import pytest
import uuid

from pulpcore.client.pulp_file import PatchedfileFileDistribution

from pulpcore.tests.functional.utils import get_from_url


@pytest.mark.parallel
def test_rbac_content_guard_full_workflow(
    rbac_contentguard_api_client,
    groups_api_client,
    groups_users_api_client,
    file_distribution_api_client,
    pulp_admin_user,
    anonymous_user,
    gen_user,
    gen_object_with_cleanup,
    monitor_task,
    file_distribution_factory,
):
    # Create all of the users and groups
    creator_user = gen_user(
        model_roles=["core.rbaccontentguard_creator", "file.filedistribution_creator"]
    )
    user_a = gen_user()
    user_b = gen_user()

    all_users = [creator_user, user_a, user_b, pulp_admin_user, anonymous_user]
    group = gen_object_with_cleanup(groups_api_client, {"name": str(uuid.uuid4())})
    groups_users_api_client.create(group.pulp_href, {"username": user_b.username})
    groups_users_api_client.create(group.pulp_href, {"username": user_a.username})

    # Create a distribution
    with creator_user:
        distro = file_distribution_factory()

    def _assert_access(authorized_users):
        """Asserts that only authorized users have access to the distribution's base_url."""
        for user in all_users:
            if user is not anonymous_user:
                auth = BasicAuth(login=user.username, password=user.password)
            else:
                auth = None
            response = get_from_url(distro.base_url, auth=auth)
            expected_status = 404 if user in authorized_users else 403
            assert response.status == expected_status, f"Failed on {user.username=}"

    # Make sure all users can access the distribution URL without a content guard
    _assert_access(all_users)

    # Check that RBAC ContentGuard can be created and assigned to a distribution
    with creator_user:
        guard = gen_object_with_cleanup(rbac_contentguard_api_client, {"name": distro.name})
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(file_distribution_api_client.partial_update(distro.pulp_href, body).task)
        distro = file_distribution_api_client.read(distro.pulp_href)
        assert guard.pulp_href == distro.content_guard

    # Check that now only the creator and admin user can access the distribution
    _assert_access([creator_user, pulp_admin_user])

    # Use the /add/ endpoint to give the users permission to access distribution
    body = {
        "users": (user_a.username, user_b.username),
        "role": "core.rbaccontentguard_downloader",
    }
    with creator_user:
        rbac_contentguard_api_client.add_role(distro.content_guard, body)
    _assert_access([creator_user, user_b, user_a, pulp_admin_user])

    # Use the /remove/ endpoint to remove users permission to access distribution
    with creator_user:
        rbac_contentguard_api_client.remove_role(distro.content_guard, body)
    _assert_access([creator_user, pulp_admin_user])

    # Use the /add/ endpoint to add group
    body = {"groups": [group.name], "role": "core.rbaccontentguard_downloader"}
    with creator_user:
        rbac_contentguard_api_client.add_role(distro.content_guard, body)
    _assert_access([creator_user, user_b, user_a, pulp_admin_user])

    # Use the /remove/ endpoint to remove group
    with creator_user:
        rbac_contentguard_api_client.remove_role(distro.content_guard, body)
    _assert_access([creator_user, pulp_admin_user])


@pytest.mark.parallel
def test_header_contentguard_workflow(
    header_contentguard_api_client,
    gen_user,
    file_distribution_factory,
    gen_object_with_cleanup,
    monitor_task,
    file_distribution_api_client,
):
    # Create all of the users and groups
    creator_user = gen_user(
        model_roles=["core.headercontentguard_creator", "file.filedistribution_creator"]
    )

    with creator_user:
        distro = file_distribution_factory()

    with creator_user:
        guard = gen_object_with_cleanup(
            header_contentguard_api_client,
            {"name": distro.name, "header_name": "x-header", "header_value": "123456"},
        )
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(file_distribution_api_client.partial_update(distro.pulp_href, body).task)
        distro = file_distribution_api_client.read(distro.pulp_href)
        assert guard.pulp_href == distro.content_guard

    # Expect to receive a 403 Forbiden
    response = get_from_url(distro.base_url, headers=None)
    assert response.status == 403

    # Expect the status to be 404 given the distribution is accessible
    # but not pointing to any publication, or repository version.
    header_value = b64encode(b"123456").decode("ascii")
    headers = {"x-header": header_value}

    response = get_from_url(distro.base_url, headers=headers)
    assert response.status == 404

    # Check the access using an jq_filter
    header_name = "x-organization"
    value_expected = "123456"
    jq_filter = ".internal.organization_id"

    with creator_user:
        distro = file_distribution_factory()

    with creator_user:
        guard = gen_object_with_cleanup(
            header_contentguard_api_client,
            {
                "name": distro.name,
                "header_name": header_name,
                "header_value": value_expected,
                "jq_filter": jq_filter,
            },
        )
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(file_distribution_api_client.partial_update(distro.pulp_href, body).task)
        distro = file_distribution_api_client.read(distro.pulp_href)
        assert guard.pulp_href == distro.content_guard

    # Expect the status to be 404 given the distribution is accesible
    # but not pointing to any publication, or repository version.
    header_content = {"internal": {"organization_id": "123456"}}
    json_header_content = json.dumps(header_content)
    byte_header_content = bytes(json_header_content, "utf8")
    header_value = b64encode(byte_header_content).decode("utf8")
    headers = {header_name: header_value}

    response = get_from_url(distro.base_url, headers=headers)
    assert response.status == 404
