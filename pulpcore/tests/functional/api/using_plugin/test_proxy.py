import pytest
from pulpcore.tests.functional.utils import PulpTaskError

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)
import sys


def _run_basic_sync_and_assert(file_bindings, monitor_task, remote, file_repo):
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Check content is present, but no artifacts are there
    content_response = file_bindings.ContentFilesApi.list(
        repository_version=f"{file_repo.versions_href}1/"
    )
    assert content_response.count == 3
    for content in content_response.results:
        assert content.artifact is None


@pytest.mark.parallel
def test_sync_http_through_http_proxy(
    file_bindings,
    file_remote_factory,
    file_repo,
    http_proxy,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing http through a http proxy.
    """
    remote_on_demand = file_remote_factory(
        manifest_path=basic_manifest_path, policy="on_demand", proxy_url=http_proxy.proxy_url
    )

    _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)


@pytest.mark.parallel
def test_sync_https_through_http_proxy(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    http_proxy,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing https through a http proxy.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="on_demand", proxy_url=http_proxy.proxy_url
    )

    _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)


@pytest.mark.parallel
def test_sync_https_through_http_proxy_with_auth(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    http_proxy_with_auth,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing https through a http proxy that requires auth.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path,
        policy="on_demand",
        tls_validation="true",
        proxy_url=http_proxy_with_auth.proxy_url,
        proxy_username=http_proxy_with_auth.username,
        proxy_password=http_proxy_with_auth.password,
    )

    _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)


@pytest.mark.parallel
def test_sync_https_through_http_proxy_with_auth_but_auth_not_configured(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    http_proxy_with_auth,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing https through a http proxy that requires auth, but auth is not configured.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path,
        policy="on_demand",
        tls_validation="true",
        proxy_url=http_proxy_with_auth.proxy_url,
    )

    try:
        _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)
    except PulpTaskError as exc:
        assert "407, message='Proxy Authentication Required'" in exc.task.error["description"]


@pytest.mark.parallel
def test_sync_http_through_https_proxy(
    file_bindings,
    file_remote_factory,
    file_repo,
    https_proxy,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing http through an https proxy.
    """
    remote_on_demand = file_remote_factory(
        manifest_path=basic_manifest_path,
        policy="on_demand",
        proxy_url=https_proxy.proxy_url,
        tls_validation="false",  # We instead should have a `proxy_insecure` option
    )

    _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)


@pytest.mark.parallel
def test_sync_https_through_https_proxy(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    https_proxy,
    basic_manifest_path,
    monitor_task,
):
    """
    Test syncing http through an https proxy.
    """
    if not (sys.version_info.major >= 3 and sys.version_info.minor >= 11):
        pytest.skip("HTTPS proxy only supported on python3.11+")
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path,
        policy="on_demand",
        proxy_url=https_proxy.proxy_url,
        tls_validation="false",
    )

    _run_basic_sync_and_assert(file_bindings, monitor_task, remote_on_demand, file_repo)
