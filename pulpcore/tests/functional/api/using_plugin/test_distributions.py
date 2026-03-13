"""Tests that perform actions over distributions."""

import pytest
import json
from urllib.parse import urljoin
from uuid import uuid4

from pulpcore.client.pulp_file.exceptions import ApiException

from pulpcore.tests.functional.utils import download_file, get_from_url


@pytest.mark.parallel
def test_crud_publication_distribution(
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_distribution_factory,
    monitor_task,
):
    # Create a remote and sync from it to create the first repository version
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = file_bindings.RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Remove content to create two more repository versions
    first_repo_version_href = file_bindings.RepositoriesFileApi.read(
        file_repo.pulp_href
    ).latest_version_href
    v1_content = file_bindings.ContentFilesApi.list(
        repository_version=first_repo_version_href
    ).results

    for i in range(2):
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                file_repo.pulp_href, {"remove_content_units": [v1_content[i].pulp_href]}
            ).task
        )

    # Create a publication from version 2
    repo_versions = file_bindings.RepositoriesFileVersionsApi.list(file_repo.pulp_href).results
    publish_data = file_bindings.FileFilePublication(repository_version=repo_versions[2].pulp_href)
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)
    distribution_data = {
        "publication": publication.pulp_href,
        "name": str(uuid4()),
        "base_path": str(uuid4()),
    }
    distribution = file_distribution_factory(**distribution_data)

    # Refresh the publication data
    publication = file_bindings.PublicationsFileApi.read(publication.pulp_href)

    # Assert on all the field values
    assert distribution.content_guard is None
    assert distribution.repository is None
    assert distribution.publication == publication.pulp_href
    assert distribution.base_path == distribution_data["base_path"]
    assert distribution.name == distribution_data["name"]

    # Assert that the publication has a reference to the distribution
    assert publication.distributions[0] == distribution.pulp_href

    # Test updating name with 'partial_update'
    new_name = str(uuid4())
    monitor_task(
        file_bindings.DistributionsFileApi.partial_update(
            distribution.pulp_href, {"name": new_name}
        ).task
    )
    distribution = file_bindings.DistributionsFileApi.read(distribution.pulp_href)
    assert distribution.name == new_name

    # Test updating base_path with 'partial_update'
    new_base_path = str(uuid4())
    monitor_task(
        file_bindings.DistributionsFileApi.partial_update(
            distribution.pulp_href, {"base_path": new_base_path}
        ).task
    )
    distribution = file_bindings.DistributionsFileApi.read(distribution.pulp_href)
    assert distribution.base_path == new_base_path

    # Test updating name with 'update'
    new_name = str(uuid4())
    distribution.name = new_name
    monitor_task(
        file_bindings.DistributionsFileApi.update(
            distribution.pulp_href, distribution.model_dump()
        ).task
    )
    distribution = file_bindings.DistributionsFileApi.read(distribution.pulp_href)
    assert distribution.name == new_name

    # Test updating base_path with 'update'
    new_base_path = str(uuid4())
    distribution.base_path = new_base_path
    monitor_task(
        file_bindings.DistributionsFileApi.update(
            distribution.pulp_href, distribution.model_dump()
        ).task
    )
    distribution = file_bindings.DistributionsFileApi.read(distribution.pulp_href)
    assert distribution.base_path == new_base_path

    # Test the generic distribution list endpoint.
    distributions = file_bindings.DistributionsFileApi.list()
    assert distribution.pulp_href in [distro.pulp_href for distro in distributions.results]

    # Delete a distribution.
    file_bindings.DistributionsFileApi.delete(distribution.pulp_href)
    with pytest.raises(ApiException):
        file_bindings.DistributionsFileApi.read(distribution.pulp_href)


@pytest.mark.parallel
def test_distribution_base_path(
    file_bindings,
    file_distribution_factory,
):
    distribution = file_distribution_factory(base_path=str(uuid4()).replace("-", "/"))

    # Test that spaces can not be part of ``base_path``.
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=str(uuid4()).replace("-", " "))
    assert json.loads(exc.value.body)["base_path"] is not None

    # Test that slash cannot be used in the beginning of ``base_path``.
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=f"/{str(uuid4())}")
    assert json.loads(exc.value.body)["base_path"] is not None

    with pytest.raises(ApiException) as exc:
        file_bindings.DistributionsFileApi.update(
            distribution.pulp_href, {"base_path": f"/{str(uuid4())}", "name": distribution.name}
        )
    assert json.loads(exc.value.body)["base_path"] is not None

    # Test that slash cannot be in the end of ``base_path``."""
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=f"{str(uuid4())}/")
    assert json.loads(exc.value.body)["base_path"] is not None

    with pytest.raises(ApiException) as exc:
        file_bindings.DistributionsFileApi.update(
            distribution.pulp_href, {"base_path": f"{str(uuid4())}/", "name": str(uuid4())}
        )
    assert json.loads(exc.value.body)["base_path"] is not None

    # Test that ``base_path`` can not be duplicated.
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=distribution.base_path)
    assert json.loads(exc.value.body)["base_path"] is not None

    # Test that distributions can't have overlapping ``base_path``.
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=distribution.base_path.rsplit("/", 1)[0])
    assert json.loads(exc.value.body)["base_path"] is not None

    base_path = "/".join((distribution.base_path, str(uuid4()).replace("-", "/")))
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(base_path=base_path)
    assert json.loads(exc.value.body)["base_path"] is not None


@pytest.mark.parallel
def test_distribution_filtering(
    file_bindings,
    file_remote_factory,
    file_random_content_unit,
    file_repository_factory,
    gen_object_with_cleanup,
    write_3_iso_file_fixture_data_factory,
    monitor_task,
):
    """Test distribution filtering based on the content exposed from the distribution."""

    def generate_repo_with_content():
        repo = file_repository_factory()
        repo_manifest_path = write_3_iso_file_fixture_data_factory(str(uuid4()))
        remote = file_remote_factory(manifest_path=repo_manifest_path, policy="on_demand")
        body = file_bindings.RepositorySyncURL(remote=remote.pulp_href)
        task_response = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task
        version_href = monitor_task(task_response).created_resources[0]
        content = file_bindings.ContentFilesApi.list(repository_version_added=version_href).results[
            0
        ]
        return repo, content

    repo1, content1 = generate_repo_with_content()

    publish_data = file_bindings.FileFilePublication(repository=repo1.pulp_href)
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)

    # test if a publication attached to a distribution exposes the published content
    data = file_bindings.FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), publication=publication.pulp_href
    )
    distribution_pub1 = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = file_bindings.DistributionsFileApi.list(with_content=content1.pulp_href).results
    assert [distribution_pub1] == results

    # test if a publication pointing to repository version no. 0 does not expose any content
    publish_data = file_bindings.FileFilePublication(repository_version=repo1.versions_href + "0/")
    publication_version_0 = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)
    data = file_bindings.FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), publication=publication_version_0.pulp_href
    )
    gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = file_bindings.DistributionsFileApi.list(with_content=content1.pulp_href).results
    assert [distribution_pub1] == results

    # test if a repository assigned to a distribution exposes the content available in the latest
    # publication for that repository's versions
    data = file_bindings.FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), repository=repo1.pulp_href
    )
    distribution_repopub = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)
    results = set(
        d.pulp_href
        for d in file_bindings.DistributionsFileApi.list(with_content=content1.pulp_href).results
    )
    assert {distribution_pub1.pulp_href, distribution_repopub.pulp_href} == results

    repo2, content2 = generate_repo_with_content()

    # add new content to the first repository to see whether the distribution filtering correctly
    # traverses to the latest publication concerning the repository under the question that should
    # contain the content
    response = file_bindings.RepositoriesFileApi.modify(
        repo1.pulp_href,
        {"remove_content_units": [], "add_content_units": [content2.pulp_href]},
    )
    monitor_task(response.task)
    assert [] == file_bindings.DistributionsFileApi.list(with_content=content2.pulp_href).results

    publish_data = file_bindings.FileFilePublication(repository=repo1.pulp_href)
    new_publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)

    # test later (20 lines below) if the publication now exposes the recently added content in the
    # affected distributions (i.e., the distribution with the reference to a repository and the
    # new one)
    data = file_bindings.FileFileDistribution(
        name="pub3", base_path="pub3", publication=new_publication.pulp_href
    )
    distribution_pub3 = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    # test if a repository without any attached publication does not expose any kind of content
    # to a user even though the content is still present in the latest repository version
    data = file_bindings.FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), repository=repo2.pulp_href
    )
    distribution_repo_only = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = set(
        d.pulp_href
        for d in file_bindings.DistributionsFileApi.list(with_content=content2.pulp_href).results
    )
    assert {distribution_pub3.pulp_href, distribution_repopub.pulp_href} == results

    # create a publication to see whether the content of the second repository is now served or not
    publish_data = file_bindings.FileFilePublication(repository=repo2.pulp_href)
    gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)

    results = set(
        d.pulp_href
        for d in file_bindings.DistributionsFileApi.list(with_content=content2.pulp_href).results
    )
    assert {
        distribution_pub3.pulp_href,
        distribution_repopub.pulp_href,
        distribution_repo_only.pulp_href,
    } == results

    # test if a random content unit is not accessible from any distribution
    results = file_bindings.DistributionsFileApi.list(
        with_content=file_random_content_unit.pulp_href
    ).results
    assert [] == results


def _get_manifest_from_distribution(distribution, distribution_base_url):
    """Download and parse PULP_MANIFEST from a distribution, returning a set of
    (name, sha256, size) tuples.
    """
    url = urljoin(distribution_base_url(distribution.base_url), "PULP_MANIFEST")
    r = download_file(url)
    files = set()
    for line in r.body.splitlines():
        files.add(tuple(line.decode().split(",")))
    return files


@pytest.mark.parallel
def test_distribution_serves_publication_content(
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
):
    """Test that publication, repository, and repository_version distributions serve
    correct content.

    Sets up a repository with two versions (v1 has 3 files, v2 has 2 files), publishes both,
    then verifies:
    - A distribution with an explicit publication serves that publication's content.
    - A distribution with ``repository`` serves the latest publication (for the latest version).
    - A distribution with ``repository_version`` serves the latest publication for that version.
    """
    # Sync to create version 1 (3 files)
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")
    body = file_bindings.RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    v1_href = file_repo.latest_version_href

    # Remove one content unit to create version 2 (2 files)
    v1_content = file_bindings.ContentFilesApi.list(repository_version=v1_href).results
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            file_repo.pulp_href, {"remove_content_units": [v1_content[0].pulp_href]}
        ).task
    )
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    v2_href = file_repo.latest_version_href

    # Publish version 1 and version 2
    pub_v1 = gen_object_with_cleanup(
        file_bindings.PublicationsFileApi,
        file_bindings.FileFilePublication(repository_version=v1_href),
    )
    pub_v2 = gen_object_with_cleanup(
        file_bindings.PublicationsFileApi,
        file_bindings.FileFilePublication(repository_version=v2_href),
    )

    # Create distributions for each method of specifying content
    distro_pub_v1 = file_distribution_factory(publication=pub_v1.pulp_href)
    distro_pub_v2 = file_distribution_factory(publication=pub_v2.pulp_href)
    distro_repo = file_distribution_factory(repository=file_repo.pulp_href)
    distro_repo_ver = file_distribution_factory(repository_version=v1_href)

    # Download manifests from each distribution
    manifest_pub_v1 = _get_manifest_from_distribution(distro_pub_v1, distribution_base_url)
    manifest_pub_v2 = _get_manifest_from_distribution(distro_pub_v2, distribution_base_url)
    manifest_repo = _get_manifest_from_distribution(distro_repo, distribution_base_url)
    manifest_repo_ver = _get_manifest_from_distribution(distro_repo_ver, distribution_base_url)

    # Sanity check: v1 and v2 publications have different content
    assert len(manifest_pub_v1) == 3
    assert len(manifest_pub_v2) == 2
    assert manifest_pub_v1 != manifest_pub_v2

    # "repository" distribution should serve the latest publication (pub_v2)
    assert manifest_repo == manifest_pub_v2

    # "repository_version" distribution pointing to v1 should serve pub_v1
    assert manifest_repo_ver == manifest_pub_v1


@pytest.mark.parallel
def test_distribution_mutually_exclusive_source(
    file_bindings,
    file_repo,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_distribution_factory,
    monitor_task,
):
    """Test that only one of publication, repository, and repository_version can be set."""
    # Sync to get a version and publication to reference
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = file_bindings.RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)
    file_repo = file_bindings.RepositoriesFileApi.read(file_repo.pulp_href)
    version_href = file_repo.latest_version_href

    publication = gen_object_with_cleanup(
        file_bindings.PublicationsFileApi,
        file_bindings.FileFilePublication(repository_version=version_href),
    )

    # repository + publication
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(repository=file_repo.pulp_href, publication=publication.pulp_href)
    assert exc.value.status == 400

    # repository + repository_version
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(repository=file_repo.pulp_href, repository_version=version_href)
    assert exc.value.status == 400

    # publication + repository_version
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(
            publication=publication.pulp_href, repository_version=version_href
        )
    assert exc.value.status == 400

    # all three
    with pytest.raises(ApiException) as exc:
        file_distribution_factory(
            repository=file_repo.pulp_href,
            publication=publication.pulp_href,
            repository_version=version_href,
        )
    assert exc.value.status == 400


@pytest.mark.parallel
def test_distribution_returns_404_without_servable_content(
    file_bindings,
    file_repository_factory,
    file_remote_ssl_factory,
    basic_manifest_path,
    gen_object_with_cleanup,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
):
    """Test that distributions return 404 when they have no servable content.

    Covers the cases where:
    - No source is set (no publication, repository, or repository_version).
    - A repository is set but has no versions (empty repo, version 0 only).
    - A repository is set but none of its versions have publications.
    - A repository_version is set but has no publication.
    """
    # Create a repo and sync it, but don't publish
    repo = file_repository_factory()
    remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    body = file_bindings.RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task)
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    v1_href = repo.latest_version_href

    # Case 1: No source set at all
    distro_empty = file_distribution_factory()
    r = get_from_url(distribution_base_url(distro_empty.base_url))
    assert r.status == 404

    # Case 2: Repository with no versions (version 0 only, no content)
    empty_repo = file_repository_factory()
    distro_empty_repo = file_distribution_factory(repository=empty_repo.pulp_href)
    r = get_from_url(distribution_base_url(distro_empty_repo.base_url))
    assert r.status == 404

    # Case 3: Repository with versions but no publications
    distro_repo_no_pub = file_distribution_factory(repository=repo.pulp_href)
    r = get_from_url(distribution_base_url(distro_repo_no_pub.base_url))
    assert r.status == 404

    # Case 4: Repository version with no publication
    distro_ver_no_pub = file_distribution_factory(repository_version=v1_href)
    r = get_from_url(distribution_base_url(distro_ver_no_pub.base_url))
    assert r.status == 404

    # Sanity check: after publishing, the repository and repository_version distributions work
    gen_object_with_cleanup(
        file_bindings.PublicationsFileApi,
        file_bindings.FileFilePublication(repository_version=v1_href),
    )
    r = get_from_url(distribution_base_url(distro_repo_no_pub.base_url))
    assert r.status == 200
    r = get_from_url(distribution_base_url(distro_ver_no_pub.base_url))
    assert r.status == 200
