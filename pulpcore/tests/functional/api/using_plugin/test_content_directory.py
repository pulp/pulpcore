import pytest


@pytest.mark.parallel
def test_hidden_distros(file_distribution_factory, pulp_content_url, http_get):
    visible = [file_distribution_factory() for _ in range(5)]
    hidden = [file_distribution_factory(hidden=True) for _ in range(5)]

    content = http_get(pulp_content_url).decode("utf-8")

    for d in visible:
        assert content.count(f'a href="{d.base_path}/"') == 1
    for d in hidden:
        assert content.count(f'a href="{d.base_path}/"') == 0


@pytest.mark.parallel
def test_zero_byte_file_listing(
    file_bindings,
    file_distribution_factory,
    file_repo_with_auto_publish,
    random_artifact_factory,
    http_get,
    monitor_task,
    pulpcore_bindings,
):
    try:
        zero_file = random_artifact_factory(size=0)
    except pulpcore_bindings.ApiException:
        zero_file = pulpcore_bindings.ArtifactsApi.list(
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ).results[0]
    task = file_bindings.ContentFilesApi.create(
        relative_path="zero",
        artifact=zero_file.pulp_href,
        repository=file_repo_with_auto_publish.pulp_href,
    ).task
    monitor_task(task)
    distribution = file_distribution_factory(repository=file_repo_with_auto_publish.pulp_href)

    response = http_get(distribution.base_url)
    z_line = [i for i in response.decode("utf-8").split("\n") if i.startswith('<a href="zero">')]
    assert len(z_line) == 1
    assert z_line[0].endswith("0 Bytes")
