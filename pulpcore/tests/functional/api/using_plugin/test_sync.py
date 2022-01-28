import uuid

from pulp_smash.pulp3.bindings import monitor_task

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)


def _run_basic_sync_and_assert(
    remote, file_repo, file_repo_api_client, content_file_api_client, policy="on_demand"
):
    body = RepositorySyncURL(remote=remote.pulp_href)
    monitor_task(file_repo_api_client.sync(file_repo.pulp_href, body).task)

    # Check content is present, but no artifacts are there
    content_response = content_file_api_client.list(
        repository_version=f"{file_repo.versions_href}1/"
    )
    assert content_response.count == 3
    for content in content_response.results:
        if policy == "immediate":
            assert content.artifact is not None
        else:
            assert content.artifact is None


def test_http_sync_no_ssl(
    delete_orphans_pre,
    file_fixture_gen_remote,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync with plain http://
    """
    remote_on_demand = file_fixture_gen_remote(fixture_name="basic", policy="on_demand")

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


def test_http_sync_ssl_tls_validation_off(
    delete_orphans_pre,
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync with https:// serving from an untrusted certificate.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(
        fixture_name="basic", policy="on_demand", tls_validation="false"
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


def test_http_sync_ssl_tls_validation_on(
    delete_orphans_pre,
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync with https:// and a client connection configured to trust it.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(
        fixture_name="basic", policy="on_demand", tls_validation="true"
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


def test_http_sync_ssl_tls_validation_defaults_to_on(
    delete_orphans_pre,
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync with https:// and that tls validation is on by default.
    """

    remote_on_demand = file_fixture_gen_remote_ssl(fixture_name="basic", policy="on_demand")

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


def test_http_sync_ssl_with_client_cert_req(
    delete_orphans_pre,
    file_fixture_gen_remote_client_cert_req,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync with https:// and mutual authentication between client and server.
    """
    remote_on_demand = file_fixture_gen_remote_client_cert_req(
        fixture_name="basic", policy="on_demand"
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )


def test_ondemand_to_immediate_sync(
    delete_orphans_pre,
    file_fixture_gen_remote_ssl,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file on_demand sync does not bring in Artifacts, but a later sync with "immediate" will.
    """
    remote_on_demand = file_fixture_gen_remote_ssl(fixture_name="basic", policy="on_demand")

    _run_basic_sync_and_assert(
        remote_on_demand,
        file_repo,
        file_repo_api_client,
        content_file_api_client,
    )

    remote_immediate = file_fixture_gen_remote_ssl(fixture_name="basic", policy="immediate")

    _run_basic_sync_and_assert(
        remote_immediate,
        file_repo,
        file_repo_api_client,
        content_file_api_client,
        policy="immediate",
    )


def test_header_for_sync(
    delete_orphans_pre,
    file_fixture_server_ssl,
    tls_certificate_authority_cert,
    file_remote_api_client,
    file_repo,
    file_repo_api_client,
    content_file_api_client,
):
    """
    Test file sync will correctly submit header data during download when configured.
    """
    requests_record = file_fixture_server_ssl.requests_record
    url = file_fixture_server_ssl.make_url("/basic/PULP_MANIFEST")

    header_name = "X-SOME-HEADER"
    header_value = str(uuid.uuid4())
    headers = [{header_name: header_value}]

    remote_on_demand = file_remote_api_client.create(
        {
            "url": str(url),
            "policy": "on_demand",
            "name": str(uuid.uuid4()),
            "ca_cert": tls_certificate_authority_cert,
            "headers": headers,
        }
    )

    _run_basic_sync_and_assert(
        remote_on_demand, file_repo, file_repo_api_client, content_file_api_client
    )

    assert len(requests_record) == 1
    assert requests_record[0].path == "/basic/PULP_MANIFEST"
    assert header_name in requests_record[0].headers
    assert header_value == requests_record[0].headers[header_name]
