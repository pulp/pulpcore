import pytest

from django.core.files.storage import default_storage
from random import sample

from pulpcore.client.pulpcore import Repair
from pulpcore.client.pulp_file import RepositorySyncURL

from pulpcore.tests.functional.utils import get_files_in_manifest


@pytest.fixture
def repository_with_corrupted_artifacts(
    pulpcore_bindings,
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    # STEP 1: sync content from a remote source
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")
    sync_data = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, sync_data).task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    # STEP 2: sample artifacts that will be modified on the filesystem later on
    content1, content2 = sample(get_files_in_manifest(remote.url), 2)

    # Modify an artifact
    artifact1_path = pulpcore_bindings.ArtifactsApi.list(sha256=content1[1]).results[0].file
    with default_storage.open(artifact1_path, "w+b") as f:
        f.write(b"$a bit rot")

    # Delete an artifact
    artifact2_path = pulpcore_bindings.ArtifactsApi.list(sha256=content2[1]).results[0].file
    default_storage.delete(artifact2_path)
    return repo


def test_repair_global_with_checksums(
    pulpcore_bindings, repository_with_corrupted_artifacts, monitor_task
):
    """Test whether missing and corrupted files can be re-downloaded.

    Do the following:

    3. Perform Pulp repair, including checksum verification.
    4. Assert that the repair task reported two corrupted and two repaired units.
    5. Repeat the Pulp repair operation.
    6. Assert that the repair task reported no missing, corrupted or repaired units.
    """
    # STEP 3
    response = pulpcore_bindings.RepairApi.post(Repair(verify_checksums=True))
    results = monitor_task(response.task)

    # STEP 4
    _verify_repair_results(results, missing=1, corrupted=1, repaired=2)

    # STEP 5
    response = pulpcore_bindings.RepairApi.post(Repair(verify_checksums=True))
    results = monitor_task(response.task)

    # STEP 6
    _verify_repair_results(results)


def test_repair_global_without_checksums(
    pulpcore_bindings, repository_with_corrupted_artifacts, monitor_task
):
    """Test whether missing files can be redownloaded.

    Do the following:

    3. Perform Pulp repair, not including checksum verification.
    4. Assert that the repair task reported one missing and one repaired unit.
    5. Repeat the Pulp repair operation.
    6. Assert that the repair task reported no missing, corrupted or repaired units.
    7. Repeat the Pulp repair operation, this time including checksum verification.
    8. Assert that the repair task reported one corrupted and one repaired unit.
    """
    # STEP 3
    response = pulpcore_bindings.RepairApi.post(Repair(verify_checksums=False))
    results = monitor_task(response.task)

    # STEP 4
    _verify_repair_results(results, missing=1, repaired=1)

    # STEP 5
    response = pulpcore_bindings.RepairApi.post(Repair(verify_checksums=False))
    results = monitor_task(response.task)

    # STEP 6
    _verify_repair_results(results)

    # STEP 7
    response = pulpcore_bindings.RepairApi.post(Repair(verify_checksums=True))
    results = monitor_task(response.task)

    # STEP 8
    _verify_repair_results(results, corrupted=1, repaired=1)


@pytest.mark.parallel
def test_repair_repository_version_with_checksums(
    file_bindings, repository_with_corrupted_artifacts, monitor_task
):
    """Test whether corrupted files can be redownloaded.

    Do the following:

    3. Repair the RepositoryVersion.
    4. Assert that the repair task reported two corrupted and two repaired units.
    5. Repeat the RepositoryVersion repair operation.
    6. Assert that the repair task reported no missing, corrupted or repaired units.
    """
    # STEP 3
    latest_version = repository_with_corrupted_artifacts.latest_version_href
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        latest_version, Repair(verify_checksums=True)
    )
    results = monitor_task(response.task)

    # STEP 4
    _verify_repair_results(results, missing=1, corrupted=1, repaired=2)

    # STEP 5
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        latest_version, Repair(verify_checksums=True)
    )
    results = monitor_task(response.task)

    # STEP 6
    _verify_repair_results(results)


@pytest.mark.parallel
def test_repair_repository_version_without_checksums(
    file_bindings, repository_with_corrupted_artifacts, monitor_task
):
    """Test whether missing files can be redownloaded.

    Do the following:

    3. Repair the RepositoryVersion, not including checksum verification.
    4. Assert that the repair task reported one missing and one repaired unit.
    5. Repeat the RepositoryVersion repair operation.
    6. Assert that the repair task reported no missing, corrupted or repaired units.
    7. Repeat the RepositoryVersion repair operation, this time including checksum verification
    8. Assert that the repair task reported one corrupted and one repaired unit.
    """
    # STEP 3
    latest_version = repository_with_corrupted_artifacts.latest_version_href
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        latest_version, Repair(verify_checksums=False)
    )
    results = monitor_task(response.task)

    # STEP 4
    _verify_repair_results(results, missing=1, repaired=1)

    # STEP 5
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        latest_version, Repair(verify_checksums=False)
    )
    results = monitor_task(response.task)

    # STEP 6
    _verify_repair_results(results)

    # STEP 7
    response = file_bindings.RepositoriesFileVersionsApi.repair(
        latest_version, Repair(verify_checksums=True)
    )
    results = monitor_task(response.task)

    # STEP 8
    _verify_repair_results(results, corrupted=1, repaired=1)


def _verify_repair_results(results, missing=0, corrupted=0, repaired=0):
    """Parse the repair task output and confirm it matches expectations."""
    progress_reports = {report.code: report for report in results.progress_reports}

    corrupted_units_report = progress_reports["repair.corrupted"]
    assert corrupted_units_report.done == corrupted, corrupted_units_report

    missing_units_report = progress_reports["repair.missing"]
    assert missing_units_report.done == missing, missing_units_report

    repaired_units_report = progress_reports["repair.repaired"]
    assert repaired_units_report.done == repaired, repaired_units_report
