"""Test that operations can be performed over tasks."""

import json
import subprocess
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
    repo_update_task = monitor_task(repo_update_action.task)

    return repo_sync_task, repo_update_task, file_repo, remote


def test_filter_tasks_by_reserved_resources(setup_filter_fixture, tasks_api_client):
    """Filter all tasks by a particular reserved resource."""
    repo_sync_task, repo_update_task, _, _ = setup_filter_fixture
    for resource in repo_update_task.reserved_resources_record:
        if "/api/v3/repositories/file/file/" in resource:
            reserved_resources_record = resource
            break
    else:
        assert False, "File repository not found in reserved_resources_record"

    results = tasks_api_client.list(reserved_resources=reserved_resources_record).results

    assert results[0].pulp_href == repo_update_task.pulp_href
    assert len(results) == 2

    # Filter all tasks by a non-existing reserved resource.
    results = tasks_api_client.list(
        reserved_resources="a_resource_should_be_never_named_like_this"
    ).results
    assert len(results) == 0

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


def get_prn(uri):
    commands = f"from pulpcore.app.util import get_prn; print(get_prn(uri='{uri}'));"
    process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)

    assert process.returncode == 0
    prn = process.stdout.decode().strip()
    return prn


def test_reserved_resources_filter(setup_filter_fixture, tasks_api_client):
    """Filter tasks using the ReservedResourcesFilter type filters."""
    repo_sync_task, repo_update_task, repo, remote = setup_filter_fixture
    task_hrefs = {repo_sync_task.pulp_href, repo_update_task.pulp_href}

    repo_prn = get_prn(repo.pulp_href)
    remote_prn = get_prn(remote.pulp_href)

    # Sanity check, TODO: remove pulp_href from filter checks in pulpcore 3.55
    assert repo_prn in repo_sync_task.reserved_resources_record
    assert f"shared:{remote_prn}" in repo_sync_task.reserved_resources_record
    assert repo_prn in repo_update_task.reserved_resources_record
    assert remote_prn not in repo_update_task.reserved_resources_record

    # reserved_resources filter
    href_results = tasks_api_client.list(reserved_resources=repo.pulp_href)
    assert href_results.count == 2
    assert set(h.pulp_href for h in href_results.results) == task_hrefs
    prn_results = tasks_api_client.list(reserved_resources=repo_prn)
    assert set(h.pulp_href for h in prn_results.results) == task_hrefs
    mixed_results = tasks_api_client.list(reserved_resources__in=[repo.pulp_href, remote_prn])
    assert mixed_results.count == 1
    assert mixed_results.results[0].pulp_href == repo_sync_task.pulp_href

    # shared_resources filter
    href_results = tasks_api_client.list(shared_resources=repo.pulp_href)
    assert href_results.count == 0
    href_results = tasks_api_client.list(shared_resources=remote.pulp_href)
    assert href_results.count == 1
    assert href_results.results[0].pulp_href == repo_sync_task.pulp_href
    prn_results = tasks_api_client.list(shared_resources=repo_prn)
    assert prn_results.count == 0
    prn_results = tasks_api_client.list(shared_resources=remote_prn)
    assert prn_results.count == 1
    assert prn_results.results[0].pulp_href == repo_sync_task.pulp_href
    mixed_results = tasks_api_client.list(shared_resources__in=[repo_prn, remote.pulp_href])
    assert mixed_results.count == 0

    # exclusive_resources filter
    href_results = tasks_api_client.list(exclusive_resources=remote.pulp_href)
    assert href_results.count == 0
    href_results = tasks_api_client.list(exclusive_resources=repo.pulp_href)
    assert href_results.count == 2
    assert set(h.pulp_href for h in href_results.results) == task_hrefs
    prn_results = tasks_api_client.list(exclusive_resources=remote_prn)
    assert prn_results.count == 0
    prn_results = tasks_api_client.list(exclusive_resources=repo_prn)
    assert set(h.pulp_href for h in prn_results.results) == task_hrefs
    mixed_results = tasks_api_client.list(exclusive_resources__in=[repo_prn, remote_prn])
    assert mixed_results.count == 0
