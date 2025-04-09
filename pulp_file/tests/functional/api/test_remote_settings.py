import pytest
import uuid

from pulpcore.client.pulp_file import (
    RepositorySyncURL,
)
from pulpcore.client.pulp_file.exceptions import BadRequestException

GOOD_CERT = """-----BEGIN CERTIFICATE-----
MIICoDCCAYgCCQC2c2uY34HNlzANBgkqhkiG9w0BAQUFADASMRAwDgYDVQQDDAdn
b3ZlZ2FuMB4XDTE5MDMxMzIxMDMzMFoXDTM4MDYxNjIxMDMzMFowEjEQMA4GA1UE
AwwHZ292ZWdhbjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANEatWsZ
1iwGmTxD02dxMI4ci+Au4FzvmWLBWD07H5GGTVFwnqmNOKhP6DHs1EsMZevkUvaG
CRxZlPYhjNFLZr2c2FnoDZ5nBXlSW6sodXURbMfyT187nDeBXVYFuh4T2eNCatnm
t3vgdi+pWsF0LbOgpu7GJI2sh5K1imxyB77tJ7PFTDZCSohkK+A+0nDCnJqDUNXD
5CK8iaBciCbnzp3nRKuM2EmgXno9Repy/HYxIgB7ZodPwDvYNjMGfvs0s9mJIKmc
CKgkPXVO9y9gaRrrytICcPOs+YoU/PN4Ttg6wzxaWvJgw44vsR8wM/0i4HlXfBdl
9br+cgn8jukDOgECAwEAATANBgkqhkiG9w0BAQUFAAOCAQEAyNHV6NA+0GfUrvBq
AHXHNnBE3nzMhGPhF/0B/dO4o0n6pgGZyzRxaUaoo6+5oQnBf/2NmDyLWdalFWX7
D1WBaxkhK+FU922+qwQKhABlwMxGCnfZ8F+rlk4lNotm3fP4wHbnO1SGIDvvZFt/
mpMgkhwL4lShUFv57YylXr+D2vSFcAryKiVGk1X3sHMXlFAMLHUm3d97fJnmb1qQ
wC43BlJCBQF98wKtYNwTUG/9gblfk8lCB2DL1hwmPy3q9KbSDOdUK3HW6a75ZzCD
6mXc/Y0bJcwweDsywbPBYP13hYUcpw4htcU6hg6DsoAjLNkSrlY+GGo7htx+L9HH
IwtfRg==
-----END CERTIFICATE-----
"""

GOOD_CERT_WITH_COMMENT = """saydas Intermédiaire CA
-----BEGIN CERTIFICATE-----
MIICoDCCAYgCCQC2c2uY34HNlzANBgkqhkiG9w0BAQUFADASMRAwDgYDVQQDDAdn
b3ZlZ2FuMB4XDTE5MDMxMzIxMDMzMFoXDTM4MDYxNjIxMDMzMFowEjEQMA4GA1UE
AwwHZ292ZWdhbjCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANEatWsZ
1iwGmTxD02dxMI4ci+Au4FzvmWLBWD07H5GGTVFwnqmNOKhP6DHs1EsMZevkUvaG
CRxZlPYhjNFLZr2c2FnoDZ5nBXlSW6sodXURbMfyT187nDeBXVYFuh4T2eNCatnm
t3vgdi+pWsF0LbOgpu7GJI2sh5K1imxyB77tJ7PFTDZCSohkK+A+0nDCnJqDUNXD
5CK8iaBciCbnzp3nRKuM2EmgXno9Repy/HYxIgB7ZodPwDvYNjMGfvs0s9mJIKmc
CKgkPXVO9y9gaRrrytICcPOs+YoU/PN4Ttg6wzxaWvJgw44vsR8wM/0i4HlXfBdl
9br+cgn8jukDOgECAwEAATANBgkqhkiG9w0BAQUFAAOCAQEAyNHV6NA+0GfUrvBq
AHXHNnBE3nzMhGPhF/0B/dO4o0n6pgGZyzRxaUaoo6+5oQnBf/2NmDyLWdalFWX7
D1WBaxkhK+FU922+qwQKhABlwMxGCnfZ8F+rlk4lNotm3fP4wHbnO1SGIDvvZFt/
mpMgkhwL4lShUFv57YylXr+D2vSFcAryKiVGk1X3sHMXlFAMLHUm3d97fJnmb1qQ
wC43BlJCBQF98wKtYNwTUG/9gblfk8lCB2DL1hwmPy3q9KbSDOdUK3HW6a75ZzCD
6mXc/Y0bJcwweDsywbPBYP13hYUcpw4htcU6hg6DsoAjLNkSrlY+GGo7htx+L9HH
IwtfRg==
-----END CERTIFICATE-----
"""

BAD_CERT = """-----BEGIN CERTIFICATE-----\nBOGUS==\n-----END CERTIFICATE-----
"""


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


@pytest.mark.parallel
def test_certificate_clean(file_remote_factory):
    # Check that a good cert validates
    a_remote = file_remote_factory(url="http://example.com/", ca_cert=GOOD_CERT)
    assert a_remote.ca_cert == GOOD_CERT
    a_remote = file_remote_factory(url="http://example.com/", client_cert=GOOD_CERT)
    assert a_remote.client_cert == GOOD_CERT

    # Check that a good-cert-with-comments validates and strips the comments
    a_remote = file_remote_factory(url="http://example.com/", ca_cert=GOOD_CERT_WITH_COMMENT)
    assert a_remote.ca_cert == GOOD_CERT
    a_remote = file_remote_factory(url="http://example.com/", client_cert=GOOD_CERT_WITH_COMMENT)
    assert a_remote.client_cert == GOOD_CERT

    # Check that a bad-cert gets rejected
    with pytest.raises(BadRequestException):
        a_remote = file_remote_factory(url="http://example.com/", ca_cert=BAD_CERT)
    with pytest.raises(BadRequestException):
        a_remote = file_remote_factory(url="http://example.com/", client_cert=BAD_CERT)
