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
    file_remote_api_client,
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
    remote = gen_object_with_cleanup(file_remote_api_client, kwargs)
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
