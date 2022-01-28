import pytest
from pulp_smash.pulp3.bindings import monitor_task, PulpTaskError

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)


def _run_basic_sync_and_assert(remote, file_repo, file_repo_api_client, content_file_api_client):
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_repo_api_client.sync(file_repo.pulp_href, body).task)

    # Check content is present, but no artifacts are there
    content_response = content_file_api_client.list(
        repository_version=f"{file_repo.versions_href}1/"
    )
    assert content_response.count == 3
    for content in content_response.results:
        assert content.artifact is None


@pytest.mark.parallel
def test_sync_http_through_http_proxy(
    file_fixture_gen_remote,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
    http_proxy,
):
    """
    Test syncing http through a http proxy.
    """
    remote_on_demand = file_fixture_gen_remote(
        fixture_name="basic", policy="on_demand", proxy_url=http_proxy.proxy_url
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


@pytest.mark.parallel
def test_sync_https_through_http_proxy(
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
    http_proxy,
):
    """
    Test syncing https through a http proxy.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(
        fixture_name="basic", policy="on_demand", proxy_url=http_proxy.proxy_url
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


@pytest.mark.parallel
def test_sync_https_through_http_proxy_with_auth(
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
    http_proxy_with_auth,
):
    """
    Test syncing https through a http proxy that requires auth.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(
        fixture_name="basic",
        policy="on_demand",
        tls_validation="true",
        proxy_url=http_proxy_with_auth.proxy_url,
        proxy_username=http_proxy_with_auth.username,
        proxy_password=http_proxy_with_auth.password,
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


@pytest.mark.parallel
def test_sync_https_through_http_proxy_with_auth_but_auth_not_configured(
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
    http_proxy_with_auth,
):
    """
    Test syncing https through a http proxy that requires auth, but auth is not configured.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(
        fixture_name="basic",
        policy="on_demand",
        tls_validation="true",
        proxy_url=http_proxy_with_auth.proxy_url,
    )

    try:
        _run_basic_sync_and_assert(
            remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
        )
    except PulpTaskError as exc:
        assert "407, message='Proxy Authentication Required'" in exc.task.error["description"]


@pytest.mark.parallel
def test_sync_http_through_https_proxy(
    file_fixture_gen_remote,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
    https_proxy,
):
    """
    Test syncing http through an https proxy.
    """
    remote_on_demand = file_fixture_gen_remote(
        fixture_name="basic",
        policy="on_demand",
        proxy_url=https_proxy.proxy_url,
        tls_validation="false",  # We instead should have a `proxy_insecure` option
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )
