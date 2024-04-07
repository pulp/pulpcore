"""Tests related to pagination."""

import pytest


@pytest.mark.parallel
def test_repo_version_pagination(
    file_content_unit_with_name_factory,
    file_bindings,
    file_repository_version_api_client,
    file_repo,
    monitor_task,
):
    # Create 20 new repository versions (21 in total)
    for i in range(20):
        content_unit = file_content_unit_with_name_factory(f"{i}.iso")
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                file_repo.pulp_href, {"add_content_units": [content_unit.pulp_href]}
            ).task
        )

    # Assert that the limit of 10 items per page of results is respected.
    first_page = file_repository_version_api_client.list(file_repo.pulp_href, limit=10, offset=0)
    assert len(first_page.results) == 10
    assert first_page.previous is None
    assert first_page.next is not None

    # Assert that a limit and an offset are respected.
    second_page = file_repository_version_api_client.list(file_repo.pulp_href, limit=10, offset=10)
    assert len(second_page.results) == 10
    assert second_page.previous is not None
    assert second_page.next is not None

    # Assert that the limit and offset are respected for the last page of results.
    third_page = file_repository_version_api_client.list(file_repo.pulp_href, limit=10, offset=20)
    assert len(third_page.results) == 1
    assert third_page.previous is not None
    assert third_page.next is None
