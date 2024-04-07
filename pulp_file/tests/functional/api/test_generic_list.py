"""Tests that look at generic list endpoints."""

import uuid

import pytest


@pytest.mark.parallel
def test_read_all_repos_generic(repositories_api_client, file_repo):
    """Ensure name is displayed when listing repositories generic."""
    response = repositories_api_client.list()
    assert response.count != 0
    for repo in response.results:
        assert repo.name is not None


@pytest.mark.parallel
def test_read_all_content_generic(content_api_client, file_random_content_unit):
    """Ensure href is displayed when listing content generic."""
    response = content_api_client.list()
    assert response.count != 0
    for content in response.results:
        assert content.pulp_href is not None


@pytest.mark.parallel
def test_read_all_content_guards_generic(
    gen_object_with_cleanup,
    content_guards_api_client,
    rbac_contentguard_api_client,
):
    """Ensure name is displayed when listing content guards generic."""
    gen_object_with_cleanup(rbac_contentguard_api_client, {"name": str(uuid.uuid4())})

    response = content_guards_api_client.list()
    assert response.count != 0
    for content_guard in response.results:
        assert content_guard.name is not None


@pytest.mark.parallel
def test_read_all_master_model_remotes_generic(
    remotes_api_client, gen_object_with_cleanup, file_remote_api_client
):
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.com"}
    remote1 = gen_object_with_cleanup(file_remote_api_client, remote_data)
    remote_data = {"name": str(uuid.uuid4()), "url": "http://example.org"}
    remote2 = gen_object_with_cleanup(file_remote_api_client, remote_data)

    response = remotes_api_client.list()
    assert response.count != 0

    hrefs = []
    for remote in response.results:
        hrefs.append(remote.pulp_href)
    assert remote1.pulp_href in hrefs
    assert remote2.pulp_href in hrefs
