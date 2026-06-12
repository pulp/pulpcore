"""Tests for file sync optimization (skipping unchanged syncs)."""

import pytest

from pulpcore.client.pulp_file import FileRepositorySyncURL

pytest.skip("Feature disabled until a future release", allow_module_level=True)


@pytest.mark.parallel
def test_sync_optimize_skips_unchanged(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that a second sync with no changes is skipped."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # First sync
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    # Second sync (unchanged) should be skipped
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert any(report.code == "sync.was_skipped" for report in task.progress_reports)

    # No new version should be created
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")


@pytest.mark.parallel
def test_sync_optimize_disabled(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that optimize=False forces a full sync even when nothing changed."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # First sync
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Second sync with optimize=False should not skip
    body = FileRepositorySyncURL(remote=remote.pulp_href, optimize=False)
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)


@pytest.mark.parallel
def test_sync_optimize_manifest_changed(
    file_bindings,
    file_repo,
    file_remote_factory,
    write_3_iso_file_fixture_data_factory,
    monitor_task,
):
    """Test that sync is not skipped when the manifest content changes."""
    manifest_path = write_3_iso_file_fixture_data_factory("optimize_manifest_changed")
    remote = file_remote_factory(manifest_path=manifest_path, policy="on_demand")

    # First sync
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    # Regenerate the fixture data with different content (different seed) at the same path
    write_3_iso_file_fixture_data_factory(
        "optimize_manifest_changed", overwrite=True, seed="different"
    )

    # Sync again with the same remote - manifest content has changed on disk
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)


@pytest.mark.parallel
def test_sync_optimize_download_policy_to_immediate(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that sync is not skipped when download policy changes to immediate."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # First sync with on_demand
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Change remote to immediate
    monitor_task(
        file_bindings.RemotesFileApi.partial_update(remote.pulp_href, {"policy": "immediate"}).task
    )

    # Sync again - should NOT be skipped because policy changed to immediate
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)


@pytest.mark.parallel
def test_sync_optimize_repository_modified(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that sync is not skipped if the repository was modified since the last sync."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # First sync
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Modify the repository by removing content
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    content = file_bindings.ContentFilesApi.list(
        repository_version=file_repo.latest_version_href
    ).results[0]
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"remove_content_units": [content.pulp_href]}
        ).task
    )

    # Sync again - should NOT be skipped because repo was modified
    task = monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)

    # The sync should have created a new version restoring the removed content
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href != version.pulp_href


@pytest.mark.parallel
def test_sync_optimize_mirror_enabled(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that sync is not skipped when switching to mirror mode."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # First sync without mirror
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Second sync with mirror=True - should NOT be skipped
    body_mirror = FileRepositorySyncURL(remote=remote.pulp_href, mirror=True)
    task = monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body_mirror).task
    )
    assert all(report.code != "sync.was_skipped" for report in task.progress_reports)


@pytest.mark.parallel
def test_sync_last_sync_details_populated(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test that last_sync_details is populated after a sync."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.last_sync_details == {}

    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.last_sync_details != {}
    assert "manifest_checksum" in file_repo.last_sync_details
    assert "url" in file_repo.last_sync_details
    assert "download_policy" in file_repo.last_sync_details
    assert "mirror" in file_repo.last_sync_details
    assert "most_recent_version" in file_repo.last_sync_details
