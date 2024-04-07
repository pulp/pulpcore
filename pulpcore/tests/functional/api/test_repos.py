"""Tests that CRUD repositories."""

from uuid import uuid4

import pytest

from pulpcore.client.pulp_file import RepositorySyncURL


@pytest.mark.parallel
def test_repository_content_filters(
    file_content_api_client,
    file_repository_api_client,
    file_repository_factory,
    file_remote_factory,
    gen_object_with_cleanup,
    write_3_iso_file_fixture_data_factory,
    monitor_task,
):
    """Test repository's content filters."""
    # generate a repo with some content
    repo = file_repository_factory()
    repo_manifest_path = write_3_iso_file_fixture_data_factory(str(uuid4()))
    remote = file_remote_factory(manifest_path=repo_manifest_path, policy="on_demand")
    body = RepositorySyncURL(remote=remote.pulp_href)
    task_response = file_repository_api_client.sync(repo.pulp_href, body).task
    version_href = monitor_task(task_response).created_resources[0]
    content = file_content_api_client.list(repository_version_added=version_href).results[0]
    repo = file_repository_api_client.read(repo.pulp_href)

    # filter repo by the content
    results = file_repository_api_client.list(with_content=content.pulp_href).results
    assert results == [repo]
    results = file_repository_api_client.list(latest_with_content=content.pulp_href).results
    assert results == [repo]

    # remove the content
    response = file_repository_api_client.modify(
        repo.pulp_href,
        {"remove_content_units": [content.pulp_href]},
    )
    monitor_task(response.task)
    repo = file_repository_api_client.read(repo.pulp_href)

    # the repo still has the content unit
    results = file_repository_api_client.list(with_content=content.pulp_href).results
    assert results == [repo]

    # but not in its latest version anymore
    results = file_repository_api_client.list(latest_with_content=content.pulp_href).results
    assert results == []


@pytest.mark.parallel
def test_repository_name_regex_filters(file_repository_factory, file_repository_api_client):
    """Test repository's name regex filters."""
    uuid = uuid4()
    repo = file_repository_factory(name=f"{uuid}-regex-test-repo")
    pattern = f"^{uuid}-regex-test.*$"

    results = file_repository_api_client.list(name__regex=pattern).results
    assert results == [repo]

    # upper case pattern
    results = file_repository_api_client.list(name__regex=pattern.upper()).results
    assert repo not in results

    # upper case pattern with iregex
    results = file_repository_api_client.list(name__iregex=pattern.upper()).results
    assert results == [repo]
