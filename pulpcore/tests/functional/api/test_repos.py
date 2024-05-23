"""Tests that CRUD repositories."""

from uuid import uuid4

import pytest
import json
import subprocess

from pulpcore.client.pulp_file import RepositorySyncURL


@pytest.mark.parallel
def test_repository_content_filters(
    file_bindings,
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
    task_response = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task
    version_href = monitor_task(task_response).created_resources[0]
    content = file_bindings.ContentFilesApi.list(repository_version_added=version_href).results[0]
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # filter repo by the content
    results = file_bindings.RepositoriesFileApi.list(with_content=content.pulp_href).results
    assert results == [repo]
    results = file_bindings.RepositoriesFileApi.list(latest_with_content=content.pulp_href).results
    assert results == [repo]

    # remove the content
    response = file_bindings.RepositoriesFileApi.modify(
        repo.pulp_href,
        {"remove_content_units": [content.pulp_href]},
    )
    monitor_task(response.task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    # the repo still has the content unit
    results = file_bindings.RepositoriesFileApi.list(with_content=content.pulp_href).results
    assert results == [repo]

    # but not in its latest version anymore
    results = file_bindings.RepositoriesFileApi.list(latest_with_content=content.pulp_href).results
    assert results == []


@pytest.mark.parallel
def test_repository_name_regex_filters(file_repository_factory, file_bindings):
    """Test repository's name regex filters."""
    uuid = uuid4()
    repo = file_repository_factory(name=f"{uuid}-regex-test-repo")
    pattern = f"^{uuid}-regex-test.*$"

    results = file_bindings.RepositoriesFileApi.list(name__regex=pattern).results
    assert results == [repo]

    # upper case pattern
    results = file_bindings.RepositoriesFileApi.list(name__regex=pattern.upper()).results
    assert repo not in results

    # upper case pattern with iregex
    results = file_bindings.RepositoriesFileApi.list(name__iregex=pattern.upper()).results
    assert results == [repo]


@pytest.mark.parallel
def test_repo_size(
    file_repo,
    file_bindings,
    file_remote_factory,
    basic_manifest_path,
    random_artifact_factory,
    monitor_task,
):
    # Sync repository with on_demand
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = {"remote": remote.pulp_href}
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    cmd = (
        "pulpcore-manager",
        "repository-size",
        "--repositories",
        file_repo.pulp_href,
        "--include-on-demand",
        "--include-versions",
    )
    run = subprocess.run(cmd, capture_output=True, check=True)
    out = json.loads(run.stdout)

    # Assert basic items of report and test on-demand sizing
    assert len(out) == 1
    report = out[0]
    assert report["name"] == file_repo.name
    assert report["href"] == file_repo.pulp_href
    assert report["disk-size"] == 0
    assert report["on-demand-size"] == 3072  # 3 * 1024
    v_report = report["versions"]
    assert len(v_report) == 2
    assert v_report[1]["version"] == 1
    assert v_report[1]["disk-size"] == 0
    assert v_report[1]["on-demand-size"] == 3072

    # Resync with immediate
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    body = {"remote": remote.pulp_href}
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    run = subprocess.run(cmd, capture_output=True, check=True)
    out = json.loads(run.stdout)

    # Check that disk-size is now filled and on-demand is 0
    report = out[0]
    assert report["disk-size"] == 3072
    assert report["on-demand-size"] == 0
    assert report["versions"][1]["disk-size"] == 3072
    assert report["versions"][1]["on-demand-size"] == 0

    # Add content unit w/ same name, but different artifact
    art1 = random_artifact_factory()
    body = {"repository": file_repo.pulp_href, "artifact": art1.pulp_href, "relative_path": "1.iso"}
    monitor_task(file_bindings.ContentFilesApi.create(**body).task)

    run = subprocess.run(cmd, capture_output=True, check=True)
    out = json.loads(run.stdout)

    # Check that repo size and repo-ver size are now different
    report = out[0]
    assert report["disk-size"] == 3072 + art1.size  # All 4 artifacts in repo
    v_report = report["versions"]
    assert len(v_report) == 3
    assert v_report[2]["disk-size"] == 2048 + art1.size  # New size of 3 artifacts in version
