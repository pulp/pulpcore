"""Tests that publish file plugin repositories."""

from aiohttp import BasicAuth
import json
import pytest
from urllib.parse import urljoin

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
    FileFilePublication,
)
from pulpcore.client.pulp_file.exceptions import ApiException
from pulpcore.tests.functional.utils import download_file


@pytest.mark.parallel
def test_crd_publications(
    file_repo,
    file_remote_ssl_factory,
    file_bindings,
    file_publication_api_client,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_random_content_unit,
    monitor_task,
):
    # Tests that a publication can be created from a specific repository version
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")

    # Sync from the remote
    initial_repo_version = file_repo.latest_version_href
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    first_repo_version_href = file_bindings.RepositoriesFileApi.read(
        file_repo.pulp_href
    ).latest_version_href
    assert first_repo_version_href.endswith("/versions/1/")

    # Add a new content unit to the repository and assert that a new repository version is created
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"add_content_units": [file_random_content_unit.pulp_href]}
        ).task
    )
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    assert file_repo.latest_version_href.endswith("/versions/2/")

    # Create a Publication using a repository and assert that its repository_version is the latest
    publish_data = FileFilePublication(repository=file_repo.pulp_href)
    publication = gen_object_with_cleanup(file_publication_api_client, publish_data)
    assert publication.repository_version == file_repo.latest_version_href
    assert publication.manifest == "PULP_MANIFEST"

    # Create a Publication using a non-latest repository version
    publish_data = FileFilePublication(repository_version=first_repo_version_href)
    publication = gen_object_with_cleanup(file_publication_api_client, publish_data)
    assert publication.repository_version == first_repo_version_href

    # Assert that a publication can't be created by specifying a repository and a repo version
    publish_data = FileFilePublication(
        repository=file_repo.pulp_href, repository_version=first_repo_version_href
    )
    with pytest.raises(ApiException) as exc:
        gen_object_with_cleanup(file_publication_api_client, publish_data)
    assert exc.value.status == 400

    # Assert that a Publication can be created using a custom manifest
    publish_data = FileFilePublication(repository=file_repo.pulp_href, manifest="listing")
    publication = gen_object_with_cleanup(file_publication_api_client, publish_data)
    assert publication.manifest == "listing"

    # Assert that a Publication can be accessed using pulp_href
    publication = file_publication_api_client.read(publication.pulp_href)

    # Read a publication by its href providing specific field list.
    config = file_bindings.RepositoriesFileApi.api_client.configuration
    auth = BasicAuth(login=config.username, password=config.password)
    full_href = urljoin(config.host, publication.pulp_href)
    for fields in [
        ("pulp_href", "pulp_created"),
        ("pulp_href", "distributions"),
        ("pulp_created", "repository", "distributions"),
    ]:
        response = download_file(f"{full_href}?fields={','.join(fields)}", auth=auth)
        assert sorted(fields) == sorted(json.loads(response.body).keys())

    # Read a publication by its href excluding specific fields.
    response = download_file(f"{full_href}?exclude_fields=created,repository", auth=auth)
    response_fields = json.loads(response.body).keys()
    assert "created" not in response_fields
    assert "repository" not in response_fields

    # Read a publication by its repository version (2 of the 3 publications should be returned)
    page = file_publication_api_client.list(repository_version=file_repo.latest_version_href)
    assert len(page.results) == 2
    for key, val in publication.to_dict().items():
        assert getattr(page.results[0], key) == val

    # Filter by repo version for which no publication exists
    page = file_publication_api_client.list(repository_version=initial_repo_version)
    assert len(page.results) == 0

    # Filter by a repo version that does not exist
    with pytest.raises(ApiException) as exc:
        invalid_version = initial_repo_version.replace("versions/0", "versions/10")
        file_publication_api_client.list(repository_version=invalid_version)
    assert exc.value.status == 400

    # Read a publication by its created time
    page = file_publication_api_client.list(pulp_created=publication.pulp_created)
    assert len(page.results) == 1
    for key, val in publication.to_dict().items():
        assert getattr(page.results[0], key) == val

    # Filter for created time for which no publication exists
    page = file_publication_api_client.list(pulp_created=file_repo.pulp_created)
    assert len(page.results) == 0

    # Assert that publications are ordered by created time
    page = file_publication_api_client.list()
    for i, pub in enumerate(page.results[:-1]):
        current = pub.pulp_created
        previous = page.results[i + 1].pulp_created
        assert current > previous

    # Delete a publication and assert that it can't be read again
    file_publication_api_client.delete(publication.pulp_href)
    with pytest.raises(ApiException) as exc:
        file_publication_api_client.read(publication.pulp_href)
    assert exc.value.status == 404
