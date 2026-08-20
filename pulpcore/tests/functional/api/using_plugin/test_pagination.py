"""Tests related to pagination."""

import pytest


@pytest.mark.parallel
def test_repo_version_pagination(
    file_bindings,
    file_repo,
    monitor_task,
    tmp_path,
):
    # Create several content units, then add them one-by-one to produce enough
    # repository versions for pagination.
    # limit=2 with 5 versions total (initial + 4) covers first/middle/last pages.
    page_size = 2
    versions_to_add = 4

    content_hrefs = []
    for i in range(versions_to_add):
        path = tmp_path / f"{i}.iso"
        path.write_bytes(f"{i}".encode())
        content_hrefs.append(
            file_bindings.ContentFilesApi.upload(file=str(path), relative_path=f"{i}.iso").pulp_href
        )

    for content_href in content_hrefs:
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                file_repo.pulp_href, {"add_content_units": [content_href]}
            ).task
        )

    # Assert that the requested limit is respected on the first page.
    first_page = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, limit=page_size, offset=0
    )
    assert len(first_page.results) == page_size
    assert first_page.previous is None
    assert first_page.next is not None

    # Assert that limit and offset are respected on a middle page.
    second_page = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, limit=page_size, offset=page_size
    )
    assert len(second_page.results) == page_size
    assert second_page.previous is not None
    assert second_page.next is not None

    # Assert the last (partial) page has previous and no next.
    third_page = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, limit=page_size, offset=page_size * 2
    )
    assert len(third_page.results) == 1
    assert third_page.previous is not None
    assert third_page.next is None
