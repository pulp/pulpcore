"""Tests that perform actions over orphan files."""
import os
import pytest

from pulpcore.app import settings


def test_orphans_delete(
    random_artifact,
    file_random_content_unit,
    artifacts_api_client,
    file_content_api_client,
    pulpcore_bindings,
    file_bindings,
    monitor_task,
):
    # Verify that the system contains the orphan content unit and the orphan artifact.
    content_unit = file_content_api_client.read(file_random_content_unit.pulp_href)
    artifact = artifacts_api_client.read(random_artifact.pulp_href)

    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        # Verify that the artifacts are on disk
        relative_path = artifacts_api_client.read(content_unit.artifact).file
        artifact_path1 = os.path.join(settings.MEDIA_ROOT, relative_path)
        artifact_path2 = os.path.join(settings.MEDIA_ROOT, artifact.file)
        assert os.path.exists(artifact_path1) is True
        assert os.path.exists(artifact_path2) is True

    # Delete orphans using deprecated API
    monitor_task(pulpcore_bindings.OrphansApi.delete().task)

    # Assert that the content unit and artifact are gone
    if settings.ORPHAN_PROTECTION_TIME == 0:
        with pytest.raises(file_bindings.ApiException) as exc:
            file_content_api_client.read(file_random_content_unit.pulp_href)
        assert exc.value.status == 404
        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            assert os.path.exists(artifact_path1) is False
            assert os.path.exists(artifact_path2) is False


def test_orphans_cleanup(
    random_artifact,
    file_random_content_unit,
    artifacts_api_client,
    file_content_api_client,
    pulpcore_bindings,
    file_bindings,
    monitor_task,
):
    # Cleanup orphans with a nonzero orphan_protection_time
    monitor_task(pulpcore_bindings.OrphansCleanupApi.cleanup({"orphan_protection_time": 10}).task)

    # Verify that the system contains the orphan content unit and the orphan artifact.
    content_unit = file_content_api_client.read(file_random_content_unit.pulp_href)
    artifact = artifacts_api_client.read(random_artifact.pulp_href)

    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        # Verify that the artifacts are on disk
        relative_path = artifacts_api_client.read(content_unit.artifact).file
        artifact_path1 = os.path.join(settings.MEDIA_ROOT, relative_path)
        artifact_path2 = os.path.join(settings.MEDIA_ROOT, artifact.file)
        assert os.path.exists(artifact_path1) is True
        assert os.path.exists(artifact_path2) is True

    # Cleanup orphans with a zero orphan_protection_time
    monitor_task(pulpcore_bindings.OrphansCleanupApi.cleanup({"orphan_protection_time": 0}).task)

    # Assert that the content unit and the artifact are gone
    with pytest.raises(file_bindings.ApiException) as exc:
        file_content_api_client.read(file_random_content_unit.pulp_href)
    assert exc.value.status == 404
    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        assert os.path.exists(artifact_path1) is False
        assert os.path.exists(artifact_path2) is False


def test_cleanup_specific_orphans(
    file_content_unit_with_name_factory,
    file_content_api_client,
    pulpcore_bindings,
    file_bindings,
    monitor_task,
):
    content_unit_1 = file_content_unit_with_name_factory("1.iso")
    content_unit_2 = file_content_unit_with_name_factory("2.iso")
    cleanup_dict = {"content_hrefs": [content_unit_1.pulp_href], "orphan_protection_time": 0}
    monitor_task(pulpcore_bindings.OrphansCleanupApi.cleanup(cleanup_dict).task)

    # Assert that content_unit_2 is gone and content_unit_1 is present
    with pytest.raises(file_bindings.ApiException) as exc:
        file_content_api_client.read(content_unit_1.pulp_href)
    assert exc.value.status == 404
    assert file_content_api_client.read(content_unit_2.pulp_href).pulp_href

    # Test whether the `content_hrefs` param raises a ValidationError with [] as the value
    content_hrefs_dict = {"content_hrefs": []}
    with pytest.raises(pulpcore_bindings.ApiException) as exc:
        pulpcore_bindings.OrphansCleanupApi.cleanup(content_hrefs_dict)
    assert exc.value.status == 400

    # Test whether the `content_hrefs` param raises a ValidationError with and invalid href"""
    content_hrefs_dict = {"content_hrefs": ["/not/a/valid/content/href"]}
    with pytest.raises(pulpcore_bindings.ApiException) as exc:
        pulpcore_bindings.OrphansCleanupApi.cleanup(content_hrefs_dict)
    assert exc.value.status == 400
