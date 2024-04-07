"""Test that operations can be performed over tasks."""

import json
from urllib.parse import urljoin
from uuid import uuid4

import pytest
from aiohttp import BasicAuth
from pulpcore.client.pulp_file import RepositorySyncURL
from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.tests.functional.utils import download_file


@pytest.fixture
def distribution(file_bindings, file_repo, gen_object_with_cleanup):
    distribution = gen_object_with_cleanup(
        file_bindings.DistributionsFileApi,
        {"name": str(uuid4()), "base_path": str(uuid4()), "repository": file_repo.pulp_href},
    )

    return distribution


@pytest.mark.parallel
def test_retrieve_task_with_fields_created_resources_only(
    bindings_cfg, tasks_api_client, distribution
):
    """Perform filtering over the task's field created_resources."""

    task = tasks_api_client.list(created_resources=distribution.pulp_href).results[0]

    auth = BasicAuth(login=bindings_cfg.username, password=bindings_cfg.password)
    full_href = urljoin(bindings_cfg.host, task.pulp_href)

    response_body = download_file(f"{full_href}?fields=created_resources", auth=auth).body

    filtered_task = json.loads(response_body)

    assert len(filtered_task["created_resources"]) == 1
    assert task.created_resources == filtered_task["created_resources"]


@pytest.fixture
def setup_filter_fixture(
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    tasks_api_client,
    monitor_task,
):
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    body = RepositorySyncURL(remote=remote.pulp_href)
    repo_sync_task = monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task
    )

    repo_update_action = file_bindings.RepositoriesFileApi.partial_update(
        file_repo.pulp_href, {"description": str(uuid4())}
    )
    repo_update_task = tasks_api_client.read(repo_update_action.task)

    return (repo_sync_task, repo_update_task)


def test_filter_tasks_by_reserved_resources(setup_filter_fixture, tasks_api_client):
    """Filter all tasks by a particular reserved resource."""
    repo_sync_task, repo_update_task = setup_filter_fixture
    reserved_resources_record = repo_update_task.reserved_resources_record[0]

    results = tasks_api_client.list(reserved_resources_record=[reserved_resources_record]).results
    # Why reserved_resources_record parameter needs to be a list here? ^

    assert results[0].pulp_href == repo_update_task.pulp_href
    assert len(results) == 2

    # Filter all tasks by a non-existing reserved resource.
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.list(
            reserved_resources_record=["a_resource_should_be_never_named_like_this"]
        )

    assert ctx.value.status == 400

    # Filter all tasks by a particular created resource.
    created_resources = repo_sync_task.created_resources[0]
    results = tasks_api_client.list(created_resources=created_resources).results

    assert len(results) == 1
    assert results[0].pulp_href == repo_sync_task.pulp_href

    # Filter all tasks by a non-existing created resource.
    created_resources = "a_resource_should_be_never_named_like_this"

    with pytest.raises(ApiException) as ctx:
        tasks_api_client.list(created_resources=created_resources)

    assert ctx.value.status == 404
