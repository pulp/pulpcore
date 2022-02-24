import logging
import uuid

from pathlib import Path

import pytest

from pulpcore.client.pulp_file import (
    ContentFilesApi,
    RepositoriesFileApi,
    RepositoriesFileVersionsApi,
    RemotesFileApi,
)
from pulp_smash.pulp3.utils import gen_repo

from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
)


_logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def file_client():
    return gen_file_client()


@pytest.fixture(scope="session")
def content_file_api_client(file_client):
    return ContentFilesApi(file_client)


@pytest.fixture(scope="session")
def file_repo_api_client(file_client):
    return RepositoriesFileApi(file_client)


@pytest.fixture(scope="session")
def file_repo_version_api_client(file_client):
    return RepositoriesFileVersionsApi(file_client)


@pytest.fixture
def file_repo(file_repo_api_client, gen_object_with_cleanup):
    return gen_object_with_cleanup(file_repo_api_client, gen_repo())


@pytest.fixture(scope="session")
def file_remote_api_client(file_client):
    return RemotesFileApi(file_client)


@pytest.fixture(scope="session")
def file_fixtures_root():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def file_fixture_server_ssl_client_cert_req(
    ssl_ctx_req_client_auth, file_fixtures_root, gen_fixture_server
):
    yield gen_fixture_server(file_fixtures_root, ssl_ctx_req_client_auth)


@pytest.fixture
def file_fixture_server_ssl(ssl_ctx, file_fixtures_root, gen_fixture_server):
    yield gen_fixture_server(file_fixtures_root, ssl_ctx)


@pytest.fixture
def file_fixture_server(file_fixtures_root, gen_fixture_server):
    yield gen_fixture_server(file_fixtures_root, None)


@pytest.fixture
def file_fixture_gen_remote(file_fixture_server, file_remote_api_client, gen_object_with_cleanup):
    def _file_fixture_gen_remote(*, fixture_name, policy, **kwargs):
        url = file_fixture_server.make_url(f"/{fixture_name}/PULP_MANIFEST")
        kwargs.update({"url": str(url), "policy": policy, "name": str(uuid.uuid4())})
        return gen_object_with_cleanup(file_remote_api_client, kwargs)

    yield _file_fixture_gen_remote


@pytest.fixture
def file_fixture_gen_remote_ssl(
    file_fixture_server_ssl,
    file_remote_api_client,
    tls_certificate_authority_cert,
    gen_object_with_cleanup,
):
    def _file_fixture_gen_remote_ssl(*, fixture_name, policy, **kwargs):
        url = file_fixture_server_ssl.make_url(f"/{fixture_name}/PULP_MANIFEST")
        kwargs.update(
            {
                "url": str(url),
                "policy": policy,
                "name": str(uuid.uuid4()),
                "ca_cert": tls_certificate_authority_cert,
            }
        )
        return gen_object_with_cleanup(file_remote_api_client, kwargs)

    yield _file_fixture_gen_remote_ssl


@pytest.fixture
def file_fixture_gen_remote_client_cert_req(
    file_fixture_server_ssl_client_cert_req,
    file_remote_api_client,
    tls_certificate_authority_cert,
    client_tls_certificate_cert_pem,
    client_tls_certificate_key_pem,
    gen_object_with_cleanup,
):
    def _file_fixture_gen_remote_client_cert_req(*, fixture_name, policy, **kwargs):
        url = file_fixture_server_ssl_client_cert_req.make_url(f"/{fixture_name}/PULP_MANIFEST")
        kwargs.update(
            {
                "url": str(url),
                "policy": policy,
                "name": str(uuid.uuid4()),
                "ca_cert": tls_certificate_authority_cert,
                "client_cert": client_tls_certificate_cert_pem,
                "client_key": client_tls_certificate_key_pem,
            }
        )
        return gen_object_with_cleanup(file_remote_api_client, kwargs)

    yield _file_fixture_gen_remote_client_cert_req


@pytest.fixture
def file_fixture_gen_file_repo(file_repo_api_client, gen_object_with_cleanup):
    """A factory to generate a File Repository with auto-deletion after the test run."""

    def _file_fixture_gen_file_repo(**kwargs):
        return gen_object_with_cleanup(file_repo_api_client, kwargs)

    yield _file_fixture_gen_file_repo
