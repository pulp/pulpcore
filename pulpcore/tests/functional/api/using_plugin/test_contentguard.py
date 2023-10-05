import json
import pytest
from pulpcore.client.pulp_file import PatchedfileFileDistribution

from base64 import b64encode

from pulp_file.tests.functional.utils import get_url


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
    response = get_url(distro.base_url, headers=None)
    assert response.status == 403

    # Expect the status to be 404 given the distribution is accessible
    # but not pointing to any publication, or repository version.
    header_value = b64encode(b"123456").decode("ascii")
    headers = {"x-header": header_value}

    response = get_url(distro.base_url, headers=headers)
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

    response = get_url(distro.base_url, headers=headers)
    assert response.status == 404
