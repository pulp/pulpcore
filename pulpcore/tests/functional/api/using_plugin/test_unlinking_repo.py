"""Tests that perform action over remotes"""

import pytest


@pytest.mark.parallel
def test_shared_remote_usage(
    file_bindings,
    file_repository_factory,
    file_content_api_client,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    """Verify remotes can be used with different repos."""
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # Create and sync repos.
    repos = [file_repository_factory() for dummy in range(4)]
    sync_tasks = [
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {"remote": remote.pulp_href}).task
        for repo in repos
    ]

    for task in sync_tasks:
        monitor_task(task)
    repos = [(file_bindings.RepositoriesFileApi.read(repo.pulp_href)) for repo in repos]

    # Compare contents of repositories.
    contents = set()
    for repo in repos:
        content = file_content_api_client.list(repository_version=repo.latest_version_href)
        assert content.count == 3
        contents.update({c.pulp_href for c in content.results})
    assert len(contents) == 3
