"""Tests related to content delivery."""

from datetime import datetime, timedelta
import re
from time import sleep
from urllib.parse import urlparse
from aiohttp import ClientResponseError
import pytest
import uuid

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)

from pulpcore.tests.functional.utils import (
    download_file,
)
from pulpcore.content.handler import Handler


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


@pytest.mark.parallel
def test_checkpoint(
    file_repository_factory,
    file_distribution_factory,
    file_content_unit_with_name_factory,
    file_bindings,
    gen_object_with_cleanup,
    monitor_task,
    http_get,
):
    """Test checkpoint."""

    def create_publication(repo, checkpoint):
        content = file_content_unit_with_name_factory(str(uuid.uuid4()))
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
        monitor_task(task)
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        pub = gen_object_with_cleanup(
            file_bindings.PublicationsFileApi,
            {"repository_version": repo.latest_version_href, "checkpoint": checkpoint},
        )
        sleep(1)
        return pub

    # setup
    repo = file_repository_factory()
    distribution = file_distribution_factory(repository=repo.pulp_href, checkpoint=True)

    pub_0 = create_publication(repo, False)
    pub_1 = create_publication(repo, True)
    pub_2 = create_publication(repo, False)
    pub_3 = create_publication(repo, True)
    pub_4 = create_publication(repo, False)

    # checkpoints listing
    response = http_get(distribution.base_url).decode("utf-8")
    checkpoints_ts = set(re.findall(r"\d{8}T\d{6}Z", response))
    assert len(checkpoints_ts) == 2
    assert Handler._format_checkpoint_timestamp(pub_1.pulp_created) in checkpoints_ts
    assert Handler._format_checkpoint_timestamp(pub_3.pulp_created) in checkpoints_ts

    # exact ts
    pub_1_url = (
        f"{distribution.base_url}{Handler._format_checkpoint_timestamp(pub_1.pulp_created)}/"
    )
    response = http_get(pub_1_url).decode("utf-8")
    assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

    # invalid ts
    with pytest.raises(ClientResponseError) as exc:
        response = http_get(f"{distribution.base_url}invalid_ts/")
    assert exc.value.status == 404

    # arbitrary ts
    pub_2_url = (
        f"{distribution.base_url}{Handler._format_checkpoint_timestamp(pub_2.pulp_created)}/"
    )
    response = http_get(pub_2_url).decode("utf-8")
    assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

    # another arbitrary ts
    pub_3_url = (
        f"{distribution.base_url}{Handler._format_checkpoint_timestamp(pub_3.pulp_created)}/"
    )
    pub_4_url = (
        f"{distribution.base_url}{Handler._format_checkpoint_timestamp(pub_4.pulp_created)}/"
    )
    response = http_get(pub_4_url).decode("utf-8")
    assert f"<h1>Index of {urlparse(pub_3_url).path}</h1>" in response

    # before first checkpoint ts
    pub_0_url = (
        f"{distribution.base_url}{Handler._format_checkpoint_timestamp(pub_0.pulp_created)}/"
    )
    with pytest.raises(ClientResponseError) as exc:
        http_get(pub_0_url).decode("utf-8")
    assert exc.value.status == 404

    # future ts
    ts = datetime.now() + timedelta(days=1)
    url = f"{distribution.base_url}{Handler._format_checkpoint_timestamp(ts)}/"
    with pytest.raises(ClientResponseError) as exc:
        http_get(url).decode("utf-8")
    assert exc.value.status == 404
