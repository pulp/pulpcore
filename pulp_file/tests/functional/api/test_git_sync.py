import pytest
import uuid

from pulpcore.tests.functional.utils import PulpTaskError

from pulpcore.client.pulp_file import RepositorySyncURL


GIT_REMOTE_URL = "https://github.com/pulp/pulp-smash.git"
FILE_COUNT = {
    "HEAD": 79,  # latest commit
    "main": 79,  # default branch
    "click": 78,  # branch
    "2016.02.18": 95,  # tag
    "63651d3": 306,  # commit for tag 2018.02.15
}


# CRUD tests


@pytest.mark.parallel
def test_git_remote_crud(file_bindings, gen_object_with_cleanup, monitor_task):
    """Test create, read, update, and delete of a FileGitRemote."""
    # Create
    body = {"name": str(uuid.uuid4()), "url": GIT_REMOTE_URL}
    remote = gen_object_with_cleanup(file_bindings.RemotesGitApi, body)
    assert remote.url == GIT_REMOTE_URL
    assert remote.git_ref == "HEAD"
    assert remote.name == body["name"]

    # Read
    remote = file_bindings.RemotesGitApi.read(remote.pulp_href)
    assert remote.url == GIT_REMOTE_URL

    # Update (partial)
    update_response = file_bindings.RemotesGitApi.partial_update(
        remote.pulp_href, {"git_ref": "main"}
    )
    monitor_task(update_response.task)
    remote = file_bindings.RemotesGitApi.read(remote.pulp_href)
    assert remote.git_ref == "main"

    # Update (full)
    new_body = {"name": str(uuid.uuid4()), "url": GIT_REMOTE_URL, "git_ref": "HEAD"}
    update_response = file_bindings.RemotesGitApi.update(remote.pulp_href, new_body)
    monitor_task(update_response.task)
    remote = file_bindings.RemotesGitApi.read(remote.pulp_href)
    assert remote.name == new_body["name"]
    assert remote.git_ref == "HEAD"


# Sync tests


@pytest.mark.parametrize("git_ref", list(FILE_COUNT.keys()))
@pytest.mark.parallel
def test_git_sync(file_bindings, file_repo, file_git_remote_factory, monitor_task, git_ref):
    """Test syncing from a public Git repository."""
    remote = file_git_remote_factory(url=GIT_REMOTE_URL, git_ref=git_ref)

    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert version.content_summary.present["file.file"]["count"] == FILE_COUNT[git_ref]
    assert version.content_summary.added["file.file"]["count"] == FILE_COUNT[git_ref]


@pytest.mark.parallel
def test_git_sync_idempotent(file_bindings, file_repo, file_git_remote_factory, monitor_task):
    """Syncing the same Git ref twice should not create a new repository version."""
    remote = file_git_remote_factory(url=GIT_REMOTE_URL, git_ref="main")

    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    first_version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    first_count = first_version.content_summary.present["file.file"]["count"]

    # Sync again -- no new version should be created
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/1/")

    second_version = file_bindings.RepositoriesFileVersionsApi.read(file_repo.latest_version_href)
    assert second_version.content_summary.present["file.file"]["count"] == first_count


@pytest.mark.parallel
def test_git_sync_invalid_url(file_bindings, file_repo, file_git_remote_factory, monitor_task):
    """Syncing with an invalid Git URL should raise a task error."""
    remote = file_git_remote_factory(url="https://invalid.example.com/no-such-repo.git")

    body = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError) as exc:
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    assert "Failed to clone git repository" in exc.value.task.error["description"]


@pytest.mark.parallel
def test_git_sync_invalid_ref(file_bindings, file_repo, file_git_remote_factory, monitor_task):
    """Syncing with a non-existent git ref should raise a task error."""
    remote = file_git_remote_factory(url=GIT_REMOTE_URL, git_ref="this-ref-does-not-exist-abc123")

    body = RepositorySyncURL(remote=remote.pulp_href)
    with pytest.raises(PulpTaskError) as exc:
        monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    error_desc = exc.value.task.error["description"]
    assert "Failed to clone" in error_desc or "Could not resolve git ref" in error_desc
