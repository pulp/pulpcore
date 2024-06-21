"""Tests related to content delivery."""

import pytest
import uuid

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)

from pulpcore.tests.functional.utils import (
    download_file,
)


@pytest.mark.parallel
def test_file_remote_on_demand(
    basic_manifest_path,
    file_distribution_factory,
    file_fixtures_root,
    file_repo_with_auto_publish,
    file_bindings,
    gen_object_with_cleanup,
    monitor_task,
):
    # Start with the path to the basic file-fixture, build a file: remote pointing into it
    file_path = str(file_fixtures_root) + basic_manifest_path
    kwargs = {
        "url": f"file://{file_path}",
        "policy": "on_demand",
        "name": str(uuid.uuid4()),
    }
    remote = gen_object_with_cleanup(file_bindings.RemotesFileApi, kwargs)
    # Sync from the remote
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    # Create a distribution from the publication
    distribution = file_distribution_factory(repository=repo.pulp_href)
    # attempt to download_file() a file
    download_file(f"{distribution.base_url}/1.iso")


@pytest.mark.parallel
def test_upload_file_on_demand_already(
    basic_manifest_path,
    file_fixtures_root,
    file_remote_factory,
    file_repo,
    file_bindings,
    monitor_task,
):
    """Test that on-demand content can be uploaded to Pulp and become immediate content."""
    remote = file_remote_factory(basic_manifest_path, policy="on_demand")
    body = {"remote": remote.pulp_href}
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    result = file_bindings.ContentFilesApi.list(repository_version=file_repo.latest_version_href)
    assert result.count == 3
    for content in result.results:
        assert content.artifact is None

    file_content = file_fixtures_root / "basic" / content.relative_path
    body = {"relative_path": content.relative_path, "file": file_content}
    task = monitor_task(file_bindings.ContentFilesApi.create(**body).task)
    assert len(task.created_resources) == 1
    assert task.created_resources[0] == content.pulp_href

    content = file_bindings.ContentFilesApi.read(content.pulp_href)
    assert content.artifact is not None
