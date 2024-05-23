"""Tests related to repository versions."""

import pytest
from random import choice
from tempfile import NamedTemporaryFile
from uuid import uuid4

from pulpcore.tests.functional.utils import PulpTaskError, get_files_in_manifest


@pytest.fixture
def file_9_contents(
    file_bindings,
    file_repository_factory,
    monitor_task,
):
    """Create 9 content units with relative paths "A" through "I"."""
    bucket_repo = file_repository_factory()
    content_units = {}
    for name in ["A", "B", "C", "D", "E", "F", "G", "H", "I"]:
        with NamedTemporaryFile() as tf:
            tf.write(name.encode())
            tf.flush()
            response = file_bindings.ContentFilesApi.create(
                relative_path=name, file=tf.name, repository=bucket_repo.pulp_href
            )
            result = monitor_task(response.task)
            content_href = next(
                (item for item in result.created_resources if "content/file/files/" in item)
            )
            content_units[name] = file_bindings.ContentFilesApi.read(content_href)
    return content_units


@pytest.fixture
def file_repository_content(
    file_bindings,
    file_remote_ssl_factory,
    file_repository_factory,
    basic_manifest_path,
    monitor_task,
):
    """Create some content that was synced into a repo on-demand."""
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    base_repo = file_repository_factory()
    task = file_bindings.RepositoriesFileApi.sync(
        base_repo.pulp_href, {"remote": remote.pulp_href}
    ).task
    monitor_task(task)
    base_repo = file_bindings.RepositoriesFileApi.read(base_repo.pulp_href)
    assert base_repo.latest_version_href[-2] == "1"
    contents = file_bindings.ContentFilesApi.list(repository_version=base_repo.latest_version_href)
    assert contents.count == 3

    return contents


@pytest.mark.parallel
def test_add_remove_content(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    """Add and remove content to a repository. Verify side-effects.

    A new repository version is automatically created each time content is
    added to or removed from a repository. Furthermore, it's possible to
    inspect any repository version and discover which content is present, which
    content was removed, and which content was added. This test case explores
    these features.
    """
    file_repo = file_repository_factory()
    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(file_repo.pulp_href)
    assert repo_versions.count == 1

    assert file_repo.latest_version_href == f"{file_repo.pulp_href}versions/0/"

    # Sync content into the repository
    CONTENT_BASE_HREF = "/api/v3/content/file/files/"
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")
    task = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, {"remote": remote.pulp_href}
    ).task
    task_report = monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)

    assert task_report.created_resources[0] == repo.latest_version_href

    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert repo_versions.count == 2

    assert repo.latest_version_href == f"{repo.pulp_href}versions/1/"

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)

    present_summary = latest_version.content_summary.present
    assert present_summary["file.file"]["count"] == 3
    base_href, _, latest_version_href = present_summary["file.file"]["href"].partition(
        "?repository_version="
    )
    assert base_href[-len(CONTENT_BASE_HREF) :] == CONTENT_BASE_HREF
    assert latest_version_href == latest_version.pulp_href == repo.latest_version_href

    added_summary = latest_version.content_summary.added
    assert added_summary["file.file"]["count"] == 3
    base_href, _, latest_version_href = added_summary["file.file"]["href"].partition(
        "?repository_version_added="
    )
    assert base_href[-len(CONTENT_BASE_HREF) :] == CONTENT_BASE_HREF
    assert latest_version_href == latest_version.pulp_href == repo.latest_version_href

    assert latest_version.content_summary.removed == {}

    # Remove content from the repository
    contents = file_bindings.ContentFilesApi.list(repository_version=repo.latest_version_href)
    assert contents.count == 3
    content = choice(contents.results)

    body = {"remove_content_units": [content.pulp_href]}
    task = file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert repo_versions.count == 3
    assert repo.latest_version_href == f"{repo.pulp_href}versions/2/"

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)

    assert latest_version.content_summary.present["file.file"]["count"] == 2

    assert latest_version.content_summary.added == {}

    removed_summary = latest_version.content_summary.removed
    assert removed_summary["file.file"]["count"] == 1
    base_href, _, latest_version_href = removed_summary["file.file"]["href"].partition(
        "?repository_version_removed="
    )
    assert base_href[-len(CONTENT_BASE_HREF) :] == CONTENT_BASE_HREF
    assert latest_version_href == latest_version.pulp_href == repo.latest_version_href

    # Add content to the repository
    body = {"add_content_units": [content.pulp_href]}
    task = file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert repo_versions.count == 4
    assert repo.latest_version_href == f"{repo.pulp_href}versions/3/"

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)

    assert latest_version.content_summary.present["file.file"]["count"] == 3
    assert latest_version.content_summary.added["file.file"]["count"] == 1
    assert latest_version.content_summary.removed == {}


@pytest.mark.parallel
def test_add_remove_repo_version(
    file_bindings,
    file_repository_factory,
    monitor_task,
    file_9_contents,
):
    """Create and delete repository versions."""
    file_repo = file_repository_factory()
    # Setup 9 content units in Pulp to populate test repository with
    contents = list(file_9_contents.values())

    # Test trying to delete version 0 on new repository
    task = file_bindings.RepositoriesFileVersionsApi.delete(file_repo.latest_version_href).task
    with pytest.raises(PulpTaskError) as e:
        monitor_task(task)
    assert "Cannot delete repository version." in e.value.task.error["description"]

    # Add versions to repository
    for content in contents:
        task = file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href[-2] == "9"

    # Test trying to delete version 0 with a populated repository
    ver_zero = f"{repo.versions_href}0/"
    monitor_task(file_bindings.RepositoriesFileVersionsApi.delete(ver_zero).task)
    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 9
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileVersionsApi.read(ver_zero)
    assert e.value.status == 404

    # Test deleting the last repository version
    last_ver = repo.latest_version_href
    monitor_task(file_bindings.RepositoriesFileVersionsApi.delete(last_ver).task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    assert repo.latest_version_href[-2] == "8"
    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 8
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileVersionsApi.read(last_ver)
    assert e.value.status == 404

    # Assert that the last added content is now gone
    latest_contents = file_bindings.ContentFilesApi.list(
        repository_version=repo.latest_version_href
    )
    assert contents[-1].pulp_href not in {c.pulp_href for c in latest_contents.results}

    # Test delete a middle version
    middle_ver = f"{repo.versions_href}4/"
    monitor_task(file_bindings.RepositoriesFileVersionsApi.delete(middle_ver).task)
    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 7
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileVersionsApi.read(middle_ver)
    assert e.value.status == 404

    # Check added count is updated properly
    next_ver = f"{repo.versions_href}5/"
    next_version = file_bindings.RepositoriesFileVersionsApi.read(next_ver)
    assert next_version.content_summary.added["file.file"]["count"] == 2
    middle_contents = file_bindings.ContentFilesApi.list(repository_version=next_ver)
    assert set(item.pulp_href for item in middle_contents.results) == set(
        item.pulp_href for item in contents[:5]
    )

    # Test attempt to delete all versions
    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    for version in versions.results[:-1]:
        task = file_bindings.RepositoriesFileVersionsApi.delete(version.pulp_href).task
    monitor_task(task)

    final_task = file_bindings.RepositoriesFileVersionsApi.delete(
        versions.results[-1].pulp_href
    ).task
    with pytest.raises(PulpTaskError) as e:
        monitor_task(final_task)

    assert "Cannot delete repository version." in e.value.task.error["description"]


@pytest.mark.parallel
def test_squash_repo_version(
    file_bindings,
    file_repository_factory,
    monitor_task,
    file_9_contents,
):
    """Test that the deletion of a repository version properly squashes the content.

    - Setup versions like:
        Version 0: <empty>
            add: ABCDE
        Version 1: ABCDE
            delete: BCDE; add: FGHI
        Version 2: AFGHI -- to be deleted
            delete: GI; add: CD
        Version 3: ACDFH -- to be squashed into
            delete: DH; add: EI
        Version 4: ACEFI
    - Delete version 2.
    - Check the content of all remaining versions.
    """
    content_units = file_9_contents
    file_repo = file_repository_factory()
    response1 = file_bindings.RepositoriesFileApi.modify(
        file_repo.pulp_href,
        {
            "add_content_units": [
                content.pulp_href
                for key, content in content_units.items()
                if key in ["A", "B", "C", "D", "E"]
            ]
        },
    )

    response2 = file_bindings.RepositoriesFileApi.modify(
        file_repo.pulp_href,
        {
            "remove_content_units": [
                content.pulp_href
                for key, content in content_units.items()
                if key in ["B", "C", "D", "E"]
            ],
            "add_content_units": [
                content.pulp_href
                for key, content in content_units.items()
                if key in ["F", "G", "H", "I"]
            ],
        },
    )

    response3 = file_bindings.RepositoriesFileApi.modify(
        file_repo.pulp_href,
        {
            "remove_content_units": [
                content.pulp_href for key, content in content_units.items() if key in ["G", "I"]
            ],
            "add_content_units": [
                content.pulp_href for key, content in content_units.items() if key in ["C", "D"]
            ],
        },
    )

    response4 = file_bindings.RepositoriesFileApi.modify(
        file_repo.pulp_href,
        {
            "remove_content_units": [
                content.pulp_href for key, content in content_units.items() if key in ["D", "H"]
            ],
            "add_content_units": [
                content.pulp_href for key, content in content_units.items() if key in ["E", "I"]
            ],
        },
    )
    version1 = file_bindings.RepositoriesFileVersionsApi.read(
        monitor_task(response1.task).created_resources[0]
    )
    version2 = file_bindings.RepositoriesFileVersionsApi.read(
        monitor_task(response2.task).created_resources[0]
    )
    version3 = file_bindings.RepositoriesFileVersionsApi.read(
        monitor_task(response3.task).created_resources[0]
    )
    version4 = file_bindings.RepositoriesFileVersionsApi.read(
        monitor_task(response4.task).created_resources[0]
    )

    # Check version state before deletion
    assert version1.content_summary.added["file.file"]["count"] == 5
    assert "file.file" not in version1.content_summary.removed
    assert version2.content_summary.added["file.file"]["count"] == 4
    assert version2.content_summary.removed["file.file"]["count"] == 4
    assert version3.content_summary.added["file.file"]["count"] == 2
    assert version3.content_summary.removed["file.file"]["count"] == 2
    assert version4.content_summary.added["file.file"]["count"] == 2
    assert version4.content_summary.removed["file.file"]["count"] == 2

    content1 = file_bindings.ContentFilesApi.list(repository_version=version1.pulp_href)
    content2 = file_bindings.ContentFilesApi.list(repository_version=version2.pulp_href)
    content3 = file_bindings.ContentFilesApi.list(repository_version=version3.pulp_href)
    content4 = file_bindings.ContentFilesApi.list(repository_version=version4.pulp_href)
    assert set((content.relative_path for content in content1.results)) == {"A", "B", "C", "D", "E"}
    assert set((content.relative_path for content in content2.results)) == {"A", "F", "G", "H", "I"}
    assert set((content.relative_path for content in content3.results)) == {"A", "C", "D", "F", "H"}
    assert set((content.relative_path for content in content4.results)) == {"A", "C", "E", "F", "I"}

    monitor_task(file_bindings.RepositoriesFileVersionsApi.delete(version2.pulp_href).task)

    # Check version state after deletion (Version 2 is gone...)
    version1 = file_bindings.RepositoriesFileVersionsApi.read(version1.pulp_href)
    version3 = file_bindings.RepositoriesFileVersionsApi.read(version3.pulp_href)
    version4 = file_bindings.RepositoriesFileVersionsApi.read(version4.pulp_href)

    assert version1.content_summary.added["file.file"]["count"] == 5
    assert "file.file" not in version1.content_summary.removed
    assert version3.content_summary.added["file.file"]["count"] == 2
    assert version3.content_summary.removed["file.file"]["count"] == 2
    assert version4.content_summary.added["file.file"]["count"] == 2
    assert version4.content_summary.removed["file.file"]["count"] == 2

    content1 = file_bindings.ContentFilesApi.list(repository_version=version1.pulp_href)
    content3 = file_bindings.ContentFilesApi.list(repository_version=version3.pulp_href)
    content4 = file_bindings.ContentFilesApi.list(repository_version=version4.pulp_href)
    assert set((content.relative_path for content in content1.results)) == {"A", "B", "C", "D", "E"}
    assert set((content.relative_path for content in content3.results)) == {"A", "C", "D", "F", "H"}
    assert set((content.relative_path for content in content4.results)) == {"A", "C", "E", "F", "I"}


@pytest.mark.parallel
def test_content_immutable_repo_version(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test whether the content present in a repo version is immutable.

    Test that POST/PUT/PATCH operations are not allowed on repository versions.
    """
    file_repo = file_repository_factory()
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    task = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, {"remote": remote.pulp_href}
    ).task
    monitor_task(task)

    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href[-2] == "1"
    repo_ver_attributes = dir(file_bindings.RepositoriesFileVersionsApi)

    # POST assertion
    for attr in repo_ver_attributes:
        assert "create" not in attr
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.client.call_api(repo.latest_version_href, "POST", auth_settings=["basicAuth"])
    assert e.value.status == 405

    body = {"base_version": f"{repo.versions_href}0/"}
    # PUT assertion
    for attr in repo_ver_attributes:
        assert "update" not in attr
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.client.call_api(
            repo.latest_version_href, "PUT", body=body, auth_settings=["basicAuth"]
        )
    assert e.value.status == 405

    # PATCH assertion
    for attr in repo_ver_attributes:
        assert "partial_update" not in attr
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.client.call_api(
            repo.latest_version_href, "PATCH", body=body, auth_settings=["basicAuth"]
        )
    assert e.value.status == 405


@pytest.mark.parallel
def test_filter_repo_version(
    file_bindings,
    file_repository_factory,
    monitor_task,
    file_9_contents,
):
    """Test whether repository versions can be filtered."""
    file_repo = file_repository_factory()
    # Setup 8 content units in Pulp to populate test repository with
    for content in file_9_contents.values():
        task = file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href[-2] == "9"
    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href).results

    # Filter repository version by invalid date.
    criteria = str(uuid4())
    for params in (
        {"pulp_created": criteria},
        {"pulp_created__gt": criteria, "pulp_created__lt": criteria},
        {"pulp_created__gte": criteria, "pulp_created__lte": criteria},
        {"pulp_created__range": [criteria, criteria]},
    ):
        with pytest.raises(file_bindings.ApiException) as e:
            file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, **params)
        assert e.value.status == 400
        assert "Enter a valid date/time." in e.value.body

    # Filter repository version by a valid date
    dates = [v.pulp_created for v in reversed(repo_versions)]
    for params, num_results in (
        ({"pulp_created": dates[0]}, 1),
        ({"pulp_created__gt": dates[0], "pulp_created__lt": dates[-1]}, len(dates) - 2),
        ({"pulp_created__gte": dates[0], "pulp_created__lte": dates[-1]}, len(dates)),
        ({"pulp_created__range": dates[0:2]}, 2),
    ):
        results = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, **params)
        assert results.count == num_results, params

    # Filter repository version by a nonexistent version number
    criteria = -1
    for params in (
        {"number": criteria},
        {"number__gt": criteria, "number__lt": criteria},
        {"number__gte": criteria, "number__lte": criteria},
        {"number__range": [criteria, criteria]},
    ):
        results = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, **params)
        assert results.count == 0, params

    # Filter repository version by an invalid version number.
    criteria = str(uuid4())
    for params in (
        {"number": criteria},
        {"number__gt": criteria, "number__lt": criteria},
        {"number__gte": criteria, "number__lte": criteria},
        {"number__range": [criteria, criteria]},
    ):
        with pytest.raises(file_bindings.ApiException) as e:
            file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, **params)
        assert e.value.status == 400
        assert "Enter a number." in e.value.body

    # Filter repository version by a valid version number
    numbers = [v.number for v in reversed(repo_versions)]
    for params, num_results in (
        ({"number": numbers[0]}, 1),
        ({"number__gt": numbers[0], "number__lt": numbers[-1]}, len(numbers) - 2),
        ({"number__gte": numbers[0], "number__lte": numbers[-1]}, len(numbers)),
        ({"number__range": numbers[0:2]}, 2),
    ):
        results = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, **params)
        assert results.count == num_results, params

    # Delete a repository version and filter by its number
    monitor_task(file_bindings.RepositoriesFileVersionsApi.delete(repo.latest_version_href).task)
    results = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href, number=numbers[-1])
    assert results.count == 0


@pytest.mark.parallel
def test_create_repo_base_version(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    file_random_content_unit,
    monitor_task,
):
    """Test whether one can create a repository version from any version."""
    # Test ``base_version`` for the same repository
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    repo = file_repository_factory()
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {"remote": remote.pulp_href}).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    base_content = file_bindings.ContentFilesApi.list(repository_version=repo.latest_version_href)
    base_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert base_version.base_version is None

    # create repo version 2
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [file_random_content_unit.pulp_href]}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    middle_content = file_bindings.ContentFilesApi.list(repository_version=repo.latest_version_href)
    assert middle_content.count == base_content.count + 1

    # create repo version 3 from version 1
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"base_version": base_version.pulp_href}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    # assert that base_version of the version 3 points to version 1
    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert latest_version.base_version == base_version.pulp_href
    # assert that content on version 1 is equal to content on version 3
    latest_content = file_bindings.ContentFilesApi.list(repository_version=repo.latest_version_href)
    assert latest_content.count == base_content.count
    assert file_random_content_unit.pulp_href not in {c.pulp_href for c in latest_content.results}

    # Test ``base_version`` for different repositories
    repo2 = file_repository_factory()
    # create a version for repo B using repo A version 1 as base_version
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo2.pulp_href, {"base_version": base_version.pulp_href}
        ).task
    )
    repo2 = file_bindings.RepositoriesFileApi.read(repo2.pulp_href)
    latest_version2 = file_bindings.RepositoriesFileVersionsApi.read(repo2.latest_version_href)

    # assert that base_version of repo B points to version 1 of repo A
    assert latest_version2.base_version == base_version.pulp_href

    # assert that content on version 1 of repo A is equal to content on version 1 repo B
    latest_content2 = file_bindings.ContentFilesApi.list(
        repository_version=repo2.latest_version_href
    )
    assert latest_content2.count == base_content.count
    assert latest_content2.results == base_content.results

    # Test ``base_version`` can be used together with other parameters
    repo3 = file_repository_factory()
    # create repo version 2 from version 1
    added_content = file_random_content_unit
    removed_content = choice(base_content.results)
    body = {
        "base_version": base_version.pulp_href,
        "add_content_units": [added_content.pulp_href],
        "remove_content_units": [removed_content.pulp_href],
    }
    monitor_task(file_bindings.RepositoriesFileApi.modify(repo3.pulp_href, body).task)
    repo3 = file_bindings.RepositoriesFileApi.read(repo3.pulp_href)
    latest_version3 = file_bindings.RepositoriesFileVersionsApi.read(repo3.latest_version_href)
    latest_content3 = file_bindings.ContentFilesApi.list(
        repository_version=repo3.latest_version_href
    )

    # assert that base_version of the version 2 points to version 1
    assert latest_version3.base_version == base_version.pulp_href
    # assert that the amount of content in version2 is the same as version 1
    assert latest_content3.count == 3
    # assert that the removed content is not present on repo version 2
    content3_hrefs = {c.pulp_href for c in latest_content3.results}
    assert removed_content.pulp_href not in content3_hrefs
    # assert that the added content is present on repo version 2
    assert added_content.pulp_href in content3_hrefs

    # Exception is raised when non-existent ``base_version`` is used
    nonexistant_version = f"{repo.versions_href}5/"
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"base_version": nonexistant_version}
        )
    assert e.value.status == 400
    assert "Object does not exist." in e.value.body


@pytest.mark.parallel
def test_filter_artifacts(
    pulpcore_bindings,
    file_bindings,
    random_artifact_factory,
    file_repository_factory,
    file_remote_ssl_factory,
    duplicate_filename_paths,
    monitor_task,
):
    """Filter artifacts by repository version."""
    file_repo = file_repository_factory()
    # Setup, add artifacts to show proper filtering
    random_artifacts = set()
    for _ in range(3):
        random_artifacts.add(random_artifact_factory().pulp_href)

    for path in duplicate_filename_paths:
        remote = file_remote_ssl_factory(manifest_path=path, policy="immediate")
        task = file_bindings.RepositoriesFileApi.sync(
            file_repo.pulp_href, {"remote": remote.pulp_href}
        ).task
        monitor_task(task)
        repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
        # Assert only three artifacts show up when filtering
        # Even on second sync only three will show up since the 3 added content units have the same
        # relative paths of current present content and thus ends up replacing them leaving the
        # total amount artifacts at 3
        artifacts = pulpcore_bindings.ArtifactsApi.list(repository_version=repo.latest_version_href)
        assert artifacts.count == 3
        assert len({a.pulp_href for a in artifacts.results}.intersection(random_artifacts)) == 0

    # Filter by invalid repository version.
    bad_version = f"{file_repo.versions_href}5/"
    with pytest.raises(pulpcore_bindings.ApiException) as e:
        pulpcore_bindings.ArtifactsApi.list(repository_version=bad_version)
    assert e.value.status == 400
    for key in ("uri", "repositoryversion", "not", "found"):
        assert key in e.value.body.lower()


@pytest.mark.parallel
def test_delete_repo_version_publication(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    monitor_task,
):
    """Test that removing a repo version will delete its publication."""
    file_repo = file_repository_factory()
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    task = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, {"remote": remote.pulp_href}
    ).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href[-2] == "1"

    pub_body = {"repository": repo.pulp_href}
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, pub_body)
    assert publication.repository_version == repo.latest_version_href

    # delete repo version used to create publication
    file_bindings.RepositoriesFileVersionsApi.delete(repo.latest_version_href)

    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.PublicationsFileApi.read(publication.pulp_href)

    assert e.value.status == 404


@pytest.mark.parallel
def test_delete_protected_repo_version(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    file_distribution_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    monitor_task,
):
    """Test that removing a repo version fails if its publication is distributed."""
    file_repo = file_repository_factory()
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    task = file_bindings.RepositoriesFileApi.sync(
        file_repo.pulp_href, {"remote": remote.pulp_href}
    ).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert repo.latest_version_href[-2] == "1"

    pub_body = {"repository": repo.pulp_href}
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, pub_body)
    assert publication.repository_version == repo.latest_version_href

    distribution = file_distribution_factory(publication=publication.pulp_href)
    assert distribution.publication == publication.pulp_href

    # deleting a protected repo version fails
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileVersionsApi.delete(repo.latest_version_href)
    assert e.value.status == 400
    assert "The repository version cannot be deleted" in e.value.body

    # unset the publication for the distribution
    task = file_bindings.DistributionsFileApi.partial_update(
        distribution.pulp_href, {"publication": ""}
    ).task
    monitor_task(task)

    # and then delete the repo version
    task = file_bindings.RepositoriesFileVersionsApi.delete(repo.latest_version_href).task
    monitor_task(task)
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert e.value.status == 404


@pytest.mark.parallel
def test_clear_all_units_repo_version(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    monitor_task,
    file_9_contents,
):
    """Test clear of all units of a given repository version."""
    # Test addition and removal of all units for a given repository version.
    repo = file_repository_factory()
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    file_bindings.RepositoriesFileApi.sync(repo.pulp_href, {"remote": remote.pulp_href})

    content = choice(list(file_9_contents.values()))
    body = {"add_content_units": [content.pulp_href], "remove_content_units": ["*"]}
    task = file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    assert repo.latest_version_href[-2] == "2"

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert latest_version.content_summary.present["file.file"]["count"] == 1
    assert latest_version.content_summary.added["file.file"]["count"] == 1
    assert latest_version.content_summary.removed["file.file"]["count"] == 3

    latest_content = file_bindings.ContentFilesApi.list(repository_version=repo.latest_version_href)
    assert latest_content.results[0] == content

    # Test clear all units using base version.
    repo = file_repository_factory()
    for content in file_9_contents.values():
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    base_version_four = f"{repo.versions_href}4/"
    body = {"base_version": base_version_four, "remove_content_units": ["*"]}
    monitor_task(file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    assert repo.latest_version_href[-3:-1] == "10"

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert latest_version.content_summary.present == {}
    assert latest_version.content_summary.added == {}
    assert latest_version.content_summary.removed["file.file"]["count"] == 9

    # Test http error is raised when invalid remove
    with pytest.raises(file_bindings.ApiException) as e:
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"remove_content_units": ["*", content.pulp_href]}
        )
    assert e.value.status == 400
    for key in ("content", "units", "*"):
        assert key in e.value.body


@pytest.mark.parallel
def test_repo_version_retention(
    file_bindings,
    file_repository_content,
    file_repository_factory,
    file_remote_ssl_factory,
    file_distribution_factory,
    basic_manifest_path,
    monitor_task,
):
    """Test retain_repo_versions for repositories."""
    # Setup
    contents = file_repository_content

    # Test repo version retention.
    repo = file_repository_factory(retain_repo_versions=1)
    for content in contents.results:
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
        monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    assert repo.latest_version_href[-2] == "3"
    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 1
    assert versions.results[0].pulp_href == repo.latest_version_href

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert latest_version.number == 3
    assert latest_version.content_summary.present["file.file"]["count"] == 3
    assert latest_version.content_summary.added["file.file"]["count"] == 3

    # Test repo version retention when retain_repo_versions is set.
    repo = file_repository_factory()
    for content in contents.results:
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
        monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 4

    # update retain_repo_versions to 2
    task = file_bindings.RepositoriesFileApi.partial_update(
        repo.pulp_href, {"retain_repo_versions": 2}
    ).task
    monitor_task(task)

    versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
    assert versions.count == 2

    latest_version = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)
    assert latest_version.number == 3
    assert latest_version.content_summary.present["file.file"]["count"] == 3
    assert latest_version.content_summary.added["file.file"]["count"] == 1

    # Test repo version retention with autopublish/autodistribute.
    body = {"retain_repo_versions": 1, "autopublish": True}
    repo = file_repository_factory(**body)
    publications = []
    for content in contents.results:
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
        monitor_task(task)
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        publications.append(
            file_bindings.PublicationsFileApi.list(
                repository_version=repo.latest_version_href
            ).results[0]
        )

    # all but the last publication should be gone
    for publication in publications[:-1]:
        with pytest.raises(file_bindings.ApiException) as ae:
            file_bindings.PublicationsFileApi.read(publication.pulp_href)
        assert ae.value.status == 404

    # check that the last publication is distributed
    distro = file_distribution_factory(repository=repo.pulp_href)
    manifest_files = get_files_in_manifest(f"{distro.base_url}PULP_MANIFEST")
    assert len(manifest_files) == contents.count


@pytest.mark.parallel
def test_repo_versions_protected_from_cleanup(
    file_bindings,
    file_repository_content,
    file_repository_factory,
    file_distribution_factory,
    gen_object_with_cleanup,
    monitor_task,
):
    """Test that distributed repo versions are protected from retain_repo_versions."""

    def _modify_and_validate(repo, content, expected_version, expected_total):
        task = file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
        monitor_task(task)

        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
        assert repo.latest_version_href[-2] == expected_version

        versions = file_bindings.RepositoriesFileVersionsApi.list(repo.pulp_href)
        assert versions.count == expected_total

        return repo

    # Setup
    contents = file_repository_content
    repo = file_repository_factory(retain_repo_versions=1)

    # Publish and distribute version 0
    publication = gen_object_with_cleanup(
        file_bindings.PublicationsFileApi, {"repository_version": repo.latest_version_href}
    )
    file_distribution_factory(publication=publication.pulp_href)

    # Version 0 is protected since it's distributed
    repo = _modify_and_validate(repo, contents.results[0], "1", 2)

    # Create a new publication and distribution which protects version 1 from deletion
    file_distribution_factory(repository=repo.pulp_href)
    publication = gen_object_with_cleanup(
        file_bindings.PublicationsFileApi, {"repository_version": repo.latest_version_href}
    )
    file_distribution_factory(publication=publication.pulp_href)

    # Create version 2 and there should be 3 versions now (2 protected)
    repo = _modify_and_validate(repo, contents.results[1], "2", 3)

    # Version 2 will be removed since we're creating version 3 and it's not protected
    _modify_and_validate(repo, contents.results[2], "3", 3)


@pytest.mark.parallel
def test_content_in_repository_version_view(
    pulpcore_bindings,
    file_bindings,
    file_repository_factory,
    file_random_content_unit,
    monitor_task,
):
    """Sync two repositories and check view filter."""
    # Test content doesn't exists.
    non_existant_content_href = (
        "/pulp/api/v3/content/file/files/c4ed74cf-a806-490d-a25f-94c3c3dd2dd7/"
    )

    with pytest.raises(pulpcore_bindings.ApiException) as e:
        pulpcore_bindings.RepositoryVersionsApi.list(content=non_existant_content_href)

    assert e.value.status == 400

    repo = file_repository_factory()
    repo2 = file_repository_factory()

    # Add content to first repo and assert repo-ver list w/ content is correct
    body = {"add_content_units": [file_random_content_unit.pulp_href]}
    task = file_bindings.RepositoriesFileApi.modify(repo.pulp_href, body).task
    monitor_task(task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    assert repo.latest_version_href[-2] == "1"

    repo_vers = pulpcore_bindings.RepositoryVersionsApi.list(
        content=file_random_content_unit.pulp_href
    )
    assert repo_vers.count == 1
    assert repo_vers.results[0].pulp_href == repo.latest_version_href

    # Add content to second repo and assert repo-ver list w/ content is larger
    task = file_bindings.RepositoriesFileApi.modify(repo2.pulp_href, body).task
    monitor_task(task)
    repo2 = file_bindings.RepositoriesFileApi.read(repo2.pulp_href)
    assert repo2.latest_version_href[-2] == "1"

    repo_vers = pulpcore_bindings.RepositoryVersionsApi.list(
        content=file_random_content_unit.pulp_href
    )
    assert repo_vers.count == 2
    assert {r.pulp_href for r in repo_vers.results} == {
        repo.latest_version_href,
        repo2.latest_version_href,
    }
