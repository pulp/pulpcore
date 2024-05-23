"""Tests related to content promotion."""

import hashlib
import pytest
from urllib.parse import urljoin

from pulpcore.tests.functional.utils import download_file, get_files_in_manifest, get_from_url

from pulpcore.client.pulp_file import RepositorySyncURL


@pytest.mark.parallel
def test_content_promotion(
    file_bindings,
    file_repo_with_auto_publish,
    file_remote_ssl_factory,
    file_distribution_factory,
    basic_manifest_path,
    monitor_task,
):
    # Create a repository, publication, and 2 distributions
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)

    # Check what content and artifacts are in the fixture repository
    expected_files = get_files_in_manifest(remote.url)

    # Sync from the remote and assert that a new repository version is created
    body = RepositorySyncURL(remote=remote.pulp_href)
    created = monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task
    ).created_resources
    pub = file_bindings.PublicationsFileApi.read(created[1])

    # Create two Distributions pointing to the publication
    distribution1 = file_distribution_factory(publication=pub.pulp_href)
    distribution2 = file_distribution_factory(publication=pub.pulp_href)
    assert distribution1.publication == pub.pulp_href
    assert distribution2.publication == pub.pulp_href

    # Create a Distribution using the repository
    distribution3 = file_distribution_factory(repository=file_repo.pulp_href)

    for distro in [distribution1, distribution2, distribution3]:
        # Assert that all 3 distributions can be accessed
        r = get_from_url(distro.base_url)
        assert r.status == 200
        # Download one of the files from the distribution and assert it has the correct checksum
        expected_files_list = list(expected_files)
        content_unit = expected_files_list[0]
        content_unit_url = urljoin(distro.base_url, content_unit[0])
        downloaded_file = download_file(content_unit_url)
        actual_checksum = hashlib.sha256(downloaded_file.body).hexdigest()
        expected_checksum = content_unit[1]
        assert expected_checksum == actual_checksum
