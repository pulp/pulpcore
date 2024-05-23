import uuid

import pytest

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)


def _run_basic_sync_and_assert(file_bindings, remote, file_repo, monitor_task):
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_bindings.RepositoriesFileApi.sync(file_repo.pulp_href, body).task)

    # Check content is present, but no artifacts are there
    content_response = file_bindings.ContentFilesApi.list(
        repository_version=f"{file_repo.versions_href}1/"
    )
    assert content_response.count == 3
    for content in content_response.results:
        if remote.policy == "immediate":
            assert content.artifact is not None
        else:
            assert content.artifact is None


@pytest.mark.parallel
def test_http_sync_no_ssl(
    file_bindings,
    file_remote_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync with plain http://
    """
    remote_on_demand = file_remote_factory(manifest_path=basic_manifest_path, policy="on_demand")

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_http_sync_ssl_tls_validation_off(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync with https:// serving from an untrusted certificate.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="on_demand", tls_validation="false"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_http_sync_ssl_tls_validation_on(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync with https:// and a client connection configured to trust it.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="on_demand", tls_validation="true"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_http_sync_ssl_tls_validation_defaults_to_on(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync with https:// and that tls validation is on by default.
    """

    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_http_sync_ssl_with_client_cert_req(
    file_bindings,
    file_remote_client_cert_req_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync with https:// and mutual authentication between client and server.
    """
    remote_on_demand = file_remote_client_cert_req_factory(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_ondemand_to_immediate_sync(
    file_bindings,
    file_remote_ssl_factory,
    file_repo,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file on_demand sync does not bring in Artifacts, but a later sync with "immediate" will.
    """
    remote_on_demand = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="on_demand"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )

    remote_immediate = file_remote_ssl_factory(
        manifest_path=basic_manifest_path, policy="immediate"
    )

    _run_basic_sync_and_assert(
        file_bindings,
        remote_immediate,
        file_repo,
        monitor_task,
    )


@pytest.mark.parallel
def test_header_for_sync(
    file_bindings,
    file_fixture_server_ssl,
    tls_certificate_authority_cert,
    file_repo,
    gen_object_with_cleanup,
    basic_manifest_path,
    monitor_task,
):
    """
    Test file sync will correctly submit header data during download when configured.
    """
    requests_record = file_fixture_server_ssl.requests_record
    url = file_fixture_server_ssl.make_url("/basic/PULP_MANIFEST")

    header_name = "X-SOME-HEADER"
    header_value = str(uuid.uuid4())
    headers = [{header_name: header_value}]

    remote_on_demand_data = {
        "url": str(url),
        "policy": "on_demand",
        "name": str(uuid.uuid4()),
        "ca_cert": tls_certificate_authority_cert,
        "headers": headers,
    }
    remote_on_demand = gen_object_with_cleanup(file_bindings.RemotesFileApi, remote_on_demand_data)

    _run_basic_sync_and_assert(
        file_bindings,
        remote_on_demand,
        file_repo,
        monitor_task,
    )

    assert len(requests_record) == 1
    assert requests_record[0].path == "/basic/PULP_MANIFEST"
    assert header_name in requests_record[0].headers
    assert header_value == requests_record[0].headers[header_name]
