import pytest

from random import sample, choice


@pytest.mark.parallel
def test_prn_schema(pulp_openapi_schema):
    """Test that PRN is a part of every serializer with a pulp_href."""
    failed = []
    for name, schema in pulp_openapi_schema["components"]["schemas"].items():
        if name.endswith("Response"):
            if "pulp_href" in schema["properties"]:
                if "prn" in schema["properties"]:
                    prn_schema = schema["properties"]["prn"]
                    if prn_schema["type"] == "string" and prn_schema["readOnly"]:
                        continue
                failed.append(name)

    assert len(failed) == 0


@pytest.mark.parallel
def test_read_prn(file_repo):
    """Test that PRN is of the form 'prn:app_label.model_label:model_pk'."""
    href = file_repo.pulp_href
    prn = f"prn:file.filerepository:{href.split('/')[-2]}"
    assert file_repo.prn == prn


@pytest.mark.parallel
def test_prn_in_filter(file_repository_factory, file_bindings):
    """Test the prn__in filter."""
    repos = [file_repository_factory() for _ in range(10)]
    prns = [r.prn for r in repos]
    selections = sample(prns, k=4)
    response = file_bindings.RepositoriesFileApi.list(prn__in=selections)
    assert response.count == 4
    assert {r.prn for r in response.results}.issubset(set(prns))


@pytest.mark.parallel
def test_create_and_filter_with_prn(
    file_bindings,
    file_repo,
    file_remote_factory,
    basic_manifest_path,
    file_publication_factory,
    file_distribution_factory,
    monitor_task,
):
    """Test that we can use PRNs to refer to any object."""
    # Creation tests
    remote = file_remote_factory(basic_manifest_path)
    task = file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, {"remote": remote.prn}).task
    task = monitor_task(task)
    assert len(task.created_resources) == 1

    repo_ver = file_bindings.RepositoriesFileVersionsApi.read(task.created_resources[0])
    pub1 = file_publication_factory(repository=file_repo.prn)
    pub2 = file_publication_factory(repository_version=repo_ver.prn)
    assert pub1.repository_version == pub2.repository_version

    dis1 = file_distribution_factory(repository=file_repo.prn)
    dis2 = file_distribution_factory(publication=pub1.prn)
    dis3 = file_distribution_factory(publication=pub2.prn)
    assert dis1.repository == file_repo.pulp_href
    assert dis2.publication == pub1.pulp_href
    assert dis3.publication == pub2.pulp_href

    # Filtering tests
    response = file_bindings.ContentFilesApi.list(repository_version=repo_ver.pulp_href)
    response2 = file_bindings.ContentFilesApi.list(repository_version=repo_ver.prn)
    assert response.count == 3
    assert response == response2

    response = file_bindings.ContentFilesApi.list(repository_version_added=repo_ver.prn)
    assert response == response2
    response = file_bindings.ContentFilesApi.list(repository_version_removed=repo_ver.prn)
    assert response.count == 0

    content_hrefs = [c.pulp_href for c in response2.results]
    content_prns = [c.prn for c in response2.results]
    cindex = choice(range(len(content_prns)))
    response = file_bindings.DistributionsFileApi.list(with_content=content_hrefs[cindex])
    response2 = file_bindings.DistributionsFileApi.list(with_content=content_prns[cindex])
    assert response.count == 3
    assert response == response2

    response = file_bindings.DistributionsFileApi.list(repository=file_repo.pulp_href)
    response2 = file_bindings.DistributionsFileApi.list(repository=file_repo.prn)
    assert response.count == 1
    assert response == response2

    response = file_bindings.PublicationsFileApi.list(content__in=content_hrefs)
    response2 = file_bindings.PublicationsFileApi.list(content__in=content_prns)
    assert response.count == 2
    assert response == response2

    response = file_bindings.PublicationsFileApi.list(repository=file_repo.pulp_href)
    response2 = file_bindings.PublicationsFileApi.list(repository=file_repo.prn)
    assert response.count == 2
    assert response == response2

    cindex = choice(range(len(content_prns)))
    response = file_bindings.RepositoriesFileApi.list(with_content=content_hrefs[cindex])
    response2 = file_bindings.RepositoriesFileApi.list(with_content=content_prns[cindex])
    assert response.count == 1
    assert response == response2
    response = file_bindings.RepositoriesFileApi.list(remote=remote.prn)
    assert response.count == 0

    response = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, content__in=content_hrefs
    )
    response2 = file_bindings.RepositoriesFileVersionsApi.list(
        file_repo.pulp_href, content__in=content_prns
    )
    assert response.count == 1
    assert response == response2
