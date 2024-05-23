"""Tests that perform actions over distributions."""

import pytest
import json
from uuid import uuid4

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
    FileFileDistribution,
    FileFilePublication,
)
from pulpcore.client.pulp_file.exceptions import ApiException


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
    body = RepositorySyncURL(remote=remote.pulp_href)
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
    publish_data = FileFilePublication(repository_version=repo_versions[2].pulp_href)
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
        file_bindings.DistributionsFileApi.update(distribution.pulp_href, distribution).task
    )
    distribution = file_bindings.DistributionsFileApi.read(distribution.pulp_href)
    assert distribution.name == new_name

    # Test updating base_path with 'update'
    new_base_path = str(uuid4())
    distribution.base_path = new_base_path
    monitor_task(
        file_bindings.DistributionsFileApi.update(distribution.pulp_href, distribution).task
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
        body = RepositorySyncURL(remote=remote.pulp_href)
        task_response = file_bindings.RepositoriesFileApi.sync(repo.pulp_href, body).task
        version_href = monitor_task(task_response).created_resources[0]
        content = file_bindings.ContentFilesApi.list(repository_version_added=version_href).results[
            0
        ]
        return repo, content

    repo1, content1 = generate_repo_with_content()

    publish_data = FileFilePublication(repository=repo1.pulp_href)
    publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)

    # test if a publication attached to a distribution exposes the published content
    data = FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), publication=publication.pulp_href
    )
    distribution_pub1 = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = file_bindings.DistributionsFileApi.list(with_content=content1.pulp_href).results
    assert [distribution_pub1] == results

    # test if a publication pointing to repository version no. 0 does not expose any content
    publish_data = FileFilePublication(repository_version=repo1.versions_href + "0/")
    publication_version_0 = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)
    data = FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), publication=publication_version_0.pulp_href
    )
    gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = file_bindings.DistributionsFileApi.list(with_content=content1.pulp_href).results
    assert [distribution_pub1] == results

    # test if a repository assigned to a distribution exposes the content available in the latest
    # publication for that repository's versions
    data = FileFileDistribution(
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

    publish_data = FileFilePublication(repository=repo1.pulp_href)
    new_publication = gen_object_with_cleanup(file_bindings.PublicationsFileApi, publish_data)

    # test later (20 lines below) if the publication now exposes the recently added content in the
    # affected distributions (i.e., the distribution with the reference to a repository and the
    # new one)
    data = FileFileDistribution(
        name="pub3", base_path="pub3", publication=new_publication.pulp_href
    )
    distribution_pub3 = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    # test if a repository without any attached publication does not expose any kind of content
    # to a user even though the content is still present in the latest repository version
    data = FileFileDistribution(
        name=str(uuid4()), base_path=str(uuid4()), repository=repo2.pulp_href
    )
    distribution_repo_only = gen_object_with_cleanup(file_bindings.DistributionsFileApi, data)

    results = set(
        d.pulp_href
        for d in file_bindings.DistributionsFileApi.list(with_content=content2.pulp_href).results
    )
    assert {distribution_pub3.pulp_href, distribution_repopub.pulp_href} == results

    # create a publication to see whether the content of the second repository is now served or not
    publish_data = FileFilePublication(repository=repo2.pulp_href)
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
