import pytest


@pytest.fixture(scope="class")
def repository_test_file(
    file_bindings,
    file_repository_factory,
    monitor_task,
    tmp_path_factory,
):
    """A repository with a single file at "test_file"."""
    filename = tmp_path_factory.mktemp("fixtures") / "test_file"
    filename.write_bytes(b"test content")
    repository = file_repository_factory(autopublish=True)
    upload_task = file_bindings.ContentFilesApi.create(
        relative_path="test_file", file=filename, repository=repository.pulp_href
    ).task
    monitor_task(upload_task)
    return repository


@pytest.fixture(params=["", "test_file"], ids=["base path", "file"])
def content_path(request):
    return request.param
