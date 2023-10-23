import aiohttp
import asyncio
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
import uuid
import warnings

import trustme
import proxy
import pytest

from aiohttp import web
from contextlib import suppress
from dataclasses import dataclass
from packaging.version import parse as parse_version
from time import sleep
from yarl import URL
from opentelemetry.proto.trace.v1.trace_pb2 import TracesData

from pulpcore.tests.functional.utils import (
    SLEEP_TIME,
    TASK_TIMEOUT,
    PulpTaskError,
    PulpTaskGroupError,
    add_recording_route,
)

from pulpcore.client.pulpcore import (
    Configuration,
    AccessPoliciesApi,
    ApiClient,
    ApiException,
    ArtifactsApi,
    ContentApi,
    ContentguardsApi,
    ContentguardsRbacApi,
    ContentguardsContentRedirectApi,
    ContentguardsHeaderApi,
    DomainsApi,
    DistributionsApi,
    ExportersPulpApi,
    ExportersPulpExportsApi,
    ExportersFilesystemApi,
    ExportersFilesystemExportsApi,
    GroupsApi,
    GroupsRolesApi,
    GroupsUsersApi,
    ImportersPulpApi,
    ImportersPulpImportsApi,
    ImportersPulpImportCheckApi,
    OrphansCleanupApi,
    PublicationsApi,
    RemotesApi,
    RepairApi,
    RepositoriesApi,
    RepositoryVersionsApi,
    RepositoriesReclaimSpaceApi,
    RolesApi,
    SigningServicesApi,
    StatusApi,
    TaskGroupsApi,
    TasksApi,
    TaskSchedulesApi,
    UploadsApi,
    UpstreamPulpsApi,
    UsersApi,
    UsersRolesApi,
    WorkersApi,
)

from .gpg_ascii_armor_signing_service import (
    _ascii_armored_detached_signing_service_name,
    ascii_armored_detached_signing_service,
    sign_with_ascii_armored_detached_signing_service,
    signing_gpg_metadata,
    pulp_trusted_public_key,
    pulp_trusted_public_key_fingerprint,
    signing_gpg_homedir_path,
    signing_script_path,
    signing_script_temp_dir,
)


class PulpTaskTimeoutError(Exception):
    """Exception to describe task and taskgroup timeout errors."""

    def __init__(self, awaitable):
        super().__init__(self, f"Timeout: {awaitable}")
        self.awaitable = awaitable


def get_bindings_config():
    api_protocol = os.environ.get("API_PROTOCOL", "https")
    api_host = os.environ.get("API_HOST", "pulp")
    api_port = os.environ.get("API_PORT", "443")
    configuration = Configuration(
        host=f"{api_protocol}://{api_host}:{api_port}",
        username=os.environ.get("ADMIN_USERNAME", "admin"),
        password=os.environ.get("ADMIN_PASSWORD", "password"),
    )
    configuration.safe_chars_for_path_param = "/"
    return configuration


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "from_pulpcore_for_all_plugins: marks tests from pulpcore as beneficial for plugins to run",
    )
    config.addinivalue_line(
        "markers",
        "parallel: marks tests as safe to run in parallel",
    )
    config.addinivalue_line(
        "markers",
        "serial: marks tests as required to run serially without any other tests also running",
    )
    config.addinivalue_line(
        "markers",
        "nightly: marks tests as intended to run during the nightly CI run",
    )


@pytest.fixture(scope="session")
def fixtures_cfg():
    @dataclass
    class FixturesConfig:
        aiohttp_fixtures_origin: str = "127.0.0.1"
        remote_fixtures_origin: str = os.environ.get(
            "REMOTE_FIXTURES_ORIGIN", "https://fixtures.pulpproject.org/"
        )

    return FixturesConfig()


# API Clients


@pytest.fixture(scope="session")
def bindings_cfg():
    return get_bindings_config()


@pytest.fixture(scope="session")
def _api_client_set():
    return set()


@pytest.fixture
def cid(_api_client_set, monkeypatch):
    value = str(uuid.uuid4())
    yield value
    print(f"Correlation-ID = {value}")


@pytest.fixture(autouse=True)
def _patch_cid_user_agent(_api_client_set, cid, monkeypatch):
    for api_client in _api_client_set:
        monkeypatch.setitem(api_client.default_headers, "Correlation-ID", cid)
        monkeypatch.setattr(
            api_client, "user_agent", os.environ.get("PYTEST_CURRENT_TEST").split(" ")[0]
        )


@pytest.fixture(scope="session")
def pulpcore_client(_api_client_set, bindings_cfg):
    api_client = ApiClient(bindings_cfg)
    _api_client_set.add(api_client)
    yield api_client
    _api_client_set.remove(api_client)


@pytest.fixture(scope="session")
def access_policies_api_client(pulpcore_client):
    return AccessPoliciesApi(pulpcore_client)


@pytest.fixture(scope="session")
def tasks_api_client(pulpcore_client):
    return TasksApi(pulpcore_client)


@pytest.fixture(scope="session")
def task_groups_api_client(pulpcore_client):
    return TaskGroupsApi(pulpcore_client)


@pytest.fixture(scope="session")
def workers_api_client(pulpcore_client):
    return WorkersApi(pulpcore_client)


@pytest.fixture(scope="session")
def artifacts_api_client(pulpcore_client):
    return ArtifactsApi(pulpcore_client)


@pytest.fixture(scope="session")
def uploads_api_client(pulpcore_client):
    return UploadsApi(pulpcore_client)


@pytest.fixture(scope="session")
def task_schedules_api_client(pulpcore_client):
    return TaskSchedulesApi(pulpcore_client)


@pytest.fixture(scope="session")
def status_api_client(pulpcore_client):
    return StatusApi(pulpcore_client)


@pytest.fixture(scope="session")
def groups_api_client(pulpcore_client):
    return GroupsApi(pulpcore_client)


@pytest.fixture(scope="session")
def groups_users_api_client(pulpcore_client):
    return GroupsUsersApi(pulpcore_client)


@pytest.fixture(scope="session")
def groups_roles_api_client(pulpcore_client):
    return GroupsRolesApi(pulpcore_client)


@pytest.fixture(scope="session")
def users_api_client(pulpcore_client):
    return UsersApi(pulpcore_client)


@pytest.fixture(scope="session")
def users_roles_api_client(pulpcore_client):
    return UsersRolesApi(pulpcore_client)


@pytest.fixture(scope="session")
def roles_api_client(pulpcore_client):
    "Provies the pulp core Roles API client object."
    return RolesApi(pulpcore_client)


@pytest.fixture(scope="session")
def content_api_client(pulpcore_client):
    return ContentApi(pulpcore_client)


@pytest.fixture(scope="session")
def domains_api_client(pulpcore_client):
    return DomainsApi(pulpcore_client)


@pytest.fixture(scope="session")
def distributions_api_client(pulpcore_client):
    return DistributionsApi(pulpcore_client)


@pytest.fixture(scope="session")
def remotes_api_client(pulpcore_client):
    return RemotesApi(pulpcore_client)


@pytest.fixture(scope="session")
def repositories_api_client(pulpcore_client):
    return RepositoriesApi(pulpcore_client)


@pytest.fixture(scope="session")
def repository_versions_api_client(pulpcore_client):
    return RepositoryVersionsApi(pulpcore_client)


@pytest.fixture(scope="session")
def publications_api_client(pulpcore_client):
    return PublicationsApi(pulpcore_client)


@pytest.fixture(scope="session")
def exporters_pulp_api_client(pulpcore_client):
    return ExportersPulpApi(pulpcore_client)


@pytest.fixture(scope="session")
def exporters_pulp_exports_api_client(pulpcore_client):
    return ExportersPulpExportsApi(pulpcore_client)


@pytest.fixture(scope="session")
def exporters_filesystem_api_client(pulpcore_client):
    return ExportersFilesystemApi(pulpcore_client)


@pytest.fixture(scope="session")
def exporters_filesystem_exports_api_client(pulpcore_client):
    return ExportersFilesystemExportsApi(pulpcore_client)


@pytest.fixture(scope="session")
def importers_pulp_api_client(pulpcore_client):
    return ImportersPulpApi(pulpcore_client)


@pytest.fixture(scope="session")
def importers_pulp_imports_api_client(pulpcore_client):
    return ImportersPulpImportsApi(pulpcore_client)


@pytest.fixture(scope="session")
def importers_pulp_imports_check_api_client(pulpcore_client):
    return ImportersPulpImportCheckApi(pulpcore_client)


@pytest.fixture(scope="session")
def signing_service_api_client(pulpcore_client):
    return SigningServicesApi(pulpcore_client)


@pytest.fixture(scope="session")
def content_guards_api_client(pulpcore_client):
    return ContentguardsApi(pulpcore_client)


@pytest.fixture(scope="session")
def rbac_contentguard_api_client(pulpcore_client):
    return ContentguardsRbacApi(pulpcore_client)


@pytest.fixture(scope="session")
def redirect_contentguard_api_client(pulpcore_client):
    return ContentguardsContentRedirectApi(pulpcore_client)


@pytest.fixture(scope="session")
def header_contentguard_api_client(pulpcore_client):
    return ContentguardsHeaderApi(pulpcore_client)


@pytest.fixture(scope="session")
def orphans_cleanup_api_client(pulpcore_client):
    return OrphansCleanupApi(pulpcore_client)


@pytest.fixture(scope="session")
def repositories_reclaim_space_api_client(pulpcore_client):
    return RepositoriesReclaimSpaceApi(pulpcore_client)


@pytest.fixture(scope="session")
def repair_api_client(pulpcore_client):
    return RepairApi(pulpcore_client)


@pytest.fixture(scope="session")
def upstream_pulp_api_client(pulpcore_client):
    return UpstreamPulpsApi(pulpcore_client)


# Threaded local fixture servers


class ThreadedAiohttpServer(threading.Thread):
    def __init__(self, app, host, port, ssl_ctx):
        super().__init__()
        self.app = app
        self.host = host
        self.port = port
        self.ssl_ctx = ssl_ctx
        self.loop = asyncio.new_event_loop()

    async def arun(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port, ssl_context=self.ssl_ctx)
        await site.start()
        async with self.shutdown_condition:
            await self.shutdown_condition.wait()
        await runner.cleanup()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.shutdown_condition = asyncio.Condition()
        self.loop.run_until_complete(self.arun())

    async def astop(self):
        async with self.shutdown_condition:
            self.shutdown_condition.notify_all()

    def stop(self):
        asyncio.run_coroutine_threadsafe(self.astop(), self.loop)


class ThreadedAiohttpServerData:
    def __init__(
        self,
        host,
        port,
        thread,
        ssl_ctx,
        requests_record,
    ):
        self.host = host
        self.port = port
        self.thread = thread
        self.ssl_ctx = ssl_ctx
        self.requests_record = requests_record

    def make_url(self, path):
        if path[0] != "/":
            raise ValueError("The `path` argument should start with a '/'")

        if self.ssl_ctx is None:
            protocol_handler = "http://"
        else:
            protocol_handler = "https://"

        return f"{protocol_handler}{self.host}:{self.port}{path}"


@pytest.fixture(scope="session")
def received_otel_span():
    """A fixture for checking the presence of specific spans on the otel collector server.

    Ensure the collector server is up and running before executing tests with this fixture. To do
    so, please, run the server as follows: python3 pulpcore/tests/functional/assets/otel_server.py
    """

    def _received_otel_span(data):
        if os.environ.get("PULP_OTEL_ENABLED") != "true":
            # pretend everything is working as expected if tests are run from
            # a non-configured runner
            return True

        async def _send_request():
            async with aiohttp.ClientSession(raise_for_status=False) as session:
                otel_server_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                async with session.post(f"{otel_server_url}/test", json=data) as response:
                    return response.status

        status = asyncio.run(_send_request())
        return True if status == 200 else False

    return _received_otel_span


# Webserver Fixtures


@pytest.fixture
def unused_port():
    def _unused_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    return _unused_port


@pytest.fixture
def gen_threaded_aiohttp_server(fixtures_cfg, unused_port):
    fixture_servers_data = []

    def _gen_threaded_aiohttp_server(app, ssl_ctx, call_record):
        host = fixtures_cfg.aiohttp_fixtures_origin
        port = unused_port()
        fixture_server = ThreadedAiohttpServer(app, host, port, ssl_ctx)
        fixture_server.daemon = True
        fixture_server.start()
        fixture_server_data = ThreadedAiohttpServerData(
            host=host,
            port=port,
            thread=fixture_server,
            requests_record=call_record,
            ssl_ctx=ssl_ctx,
        )
        fixture_servers_data.append(fixture_server_data)
        return fixture_server_data

    yield _gen_threaded_aiohttp_server

    for fixture_server_data in fixture_servers_data:
        fixture_server_data.thread.stop()

    for fixture_server_data in fixture_servers_data:
        fixture_server_data.thread.join()


@pytest.fixture
def gen_fixture_server(gen_threaded_aiohttp_server):
    def _gen_fixture_server(fixtures_root, ssl_ctx):
        app = web.Application()
        call_record = add_recording_route(app, fixtures_root)
        return gen_threaded_aiohttp_server(app, ssl_ctx, call_record)

    yield _gen_fixture_server


# Proxy Fixtures


@pytest.fixture
def http_proxy(fixtures_cfg, unused_port):
    host = fixtures_cfg.aiohttp_fixtures_origin
    port = unused_port()
    proxypy_args = [
        "--num-workers",
        "4",
        "--hostname",
        host,
        "--port",
        str(port),
    ]

    proxy_data = ProxyData(host=host, port=port)

    with proxy.Proxy(input_args=proxypy_args):
        yield proxy_data


@pytest.fixture
def http_proxy_with_auth(fixtures_cfg, unused_port):
    host = fixtures_cfg.aiohttp_fixtures_origin
    port = unused_port()

    username = str(uuid.uuid4())
    password = str(uuid.uuid4())

    proxypy_args = [
        "--num-workers",
        "4",
        "--hostname",
        host,
        "--port",
        str(port),
        "--basic-auth",
        f"{username}:{password}",
    ]

    proxy_data = ProxyData(host=host, port=port, username=username, password=password)

    with proxy.Proxy(input_args=proxypy_args):
        yield proxy_data


@pytest.fixture
def https_proxy(fixtures_cfg, unused_port, proxy_tls_certificate_pem_path):
    host = fixtures_cfg.aiohttp_fixtures_origin
    port = unused_port()

    proxypy_args = [
        "--num-workers",
        "4",
        "--hostname",
        host,
        "--port",
        str(port),
        "--cert-file",
        proxy_tls_certificate_pem_path,  # contains both key and cert
        "--key-file",
        proxy_tls_certificate_pem_path,  # contains both key and cert
    ]

    proxy_data = ProxyData(host=host, port=port, ssl=True)  # TODO update me

    with proxy.Proxy(input_args=proxypy_args):
        yield proxy_data


class ProxyData:
    def __init__(self, *, host, port, username=None, password=None, ssl=False):
        self.host = host
        self.port = port

        self.username = username
        self.password = password

        self.ssl = ssl

        if ssl:
            scheme = "https"
        else:
            scheme = "http"

        self.proxy_url = str(
            URL.build(
                scheme=scheme,
                host=self.host,
                port=self.port,
            )
        )


# Server Side TLS Fixtures


@pytest.fixture(scope="session")
def tls_certificate_authority():
    return trustme.CA()


@pytest.fixture
def tls_certificate_authority_cert(tls_certificate_authority):
    return tls_certificate_authority.cert_pem.bytes().decode()


@pytest.fixture
def tls_certificate(fixtures_cfg, tls_certificate_authority):
    return tls_certificate_authority.issue_cert(
        fixtures_cfg.aiohttp_fixtures_origin,
    )


# Proxy TLS Fixtures


@pytest.fixture(scope="session")
def proxy_tls_certificate_authority():
    return trustme.CA()


@pytest.fixture
def proxy_tls_certificate(fixtures_cfg, client_tls_certificate_authority):
    return client_tls_certificate_authority.issue_cert(
        fixtures_cfg.aiohttp_fixtures_origin,
    )


@pytest.fixture
def proxy_tls_certificate_pem_path(proxy_tls_certificate):
    with proxy_tls_certificate.private_key_and_cert_chain_pem.tempfile() as cert_pem:
        yield cert_pem


# Client Side TLS Fixtures


@pytest.fixture(scope="session")
def client_tls_certificate_authority():
    return trustme.CA()


@pytest.fixture
def client_tls_certificate_authority_pem_path(client_tls_certificate_authority):
    with client_tls_certificate_authority.cert_pem.tempfile() as client_ca_pem:
        yield client_ca_pem


@pytest.fixture
def client_tls_certificate(fixtures_cfg, client_tls_certificate_authority):
    return client_tls_certificate_authority.issue_cert(
        fixtures_cfg.aiohttp_fixtures_origin,
    )


@pytest.fixture
def client_tls_certificate_cert_pem(client_tls_certificate):
    return client_tls_certificate.cert_chain_pems[0].bytes().decode()


@pytest.fixture
def client_tls_certificate_key_pem(client_tls_certificate):
    return client_tls_certificate.private_key_pem.bytes().decode()


# SSL Context Fixtures


@pytest.fixture
def ssl_ctx(tls_certificate):
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_certificate.configure_cert(ssl_ctx)
    return ssl_ctx


@pytest.fixture
def ssl_ctx_req_client_auth(
    tls_certificate, client_tls_certificate, client_tls_certificate_authority_pem_path
):
    ssl_ctx = ssl.create_default_context(
        purpose=ssl.Purpose.CLIENT_AUTH, cafile=client_tls_certificate_authority_pem_path
    )
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    tls_certificate.configure_cert(ssl_ctx)
    return ssl_ctx


# Object factories


@pytest.fixture
def role_factory(roles_api_client, gen_object_with_cleanup):
    def _role_factory(**kwargs):
        return gen_object_with_cleanup(roles_api_client, kwargs)

    return _role_factory


@pytest.fixture
def gen_user(bindings_cfg, users_api_client, users_roles_api_client, gen_object_with_cleanup):
    class user_context:
        def __init__(self, username=None, model_roles=None, object_roles=None, domain_roles=None):
            self.username = username or str(uuid.uuid4())
            self.password = str(uuid.uuid4())
            self.user = gen_object_with_cleanup(
                users_api_client, {"username": self.username, "password": self.password}
            )
            self._saved_credentials = []

            if model_roles:
                for role in model_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "domain": None, "content_object": None},
                    )
            if domain_roles:
                for role, domain in domain_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "domain": domain, "content_object": None},
                    )
            if object_roles:
                for role, content_object in object_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "domain": None, "content_object": content_object},
                    )

        def __enter__(self):
            self._saved_credentials.append((bindings_cfg.username, bindings_cfg.password))
            bindings_cfg.username, bindings_cfg.password = self.username, self.password
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = self._saved_credentials.pop()

    return user_context


@pytest.fixture(scope="session")
def anonymous_user(bindings_cfg):
    class AnonymousUser:
        def __init__(self):
            self._saved_credentials = []

        def __enter__(self):
            self._saved_credentials.append((bindings_cfg.username, bindings_cfg.password))
            bindings_cfg.username, bindings_cfg.password = None, None
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = self._saved_credentials.pop()

    return AnonymousUser()


@pytest.fixture(scope="session")
def invalid_user(bindings_cfg):
    class InvalidUser:
        def __init__(self):
            self._saved_credentials = []

        def __enter__(self):
            self._saved_credentials.append((bindings_cfg.username, bindings_cfg.password))
            bindings_cfg.username, bindings_cfg.password = str(uuid.uuid4()), str(uuid.uuid4())
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = self._saved_credentials.pop()

    return InvalidUser()


@pytest.fixture(scope="session")
def pulp_admin_user(bindings_cfg):
    class AdminUser:
        def __init__(self):
            self.username = bindings_cfg.username
            self.password = bindings_cfg.password
            self._saved_credentials = []

        def __enter__(self):
            self._saved_credentials.append((bindings_cfg.username, bindings_cfg.password))
            bindings_cfg.username, bindings_cfg.password = self.username, self.password
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = self._saved_credentials.pop()

    return AdminUser()


@pytest.fixture
def random_artifact_factory(
    artifacts_api_client, tmp_path, gen_object_with_cleanup, pulp_domain_enabled
):
    def _random_artifact_factory(size=32, pulp_domain=None):
        kwargs = {}
        if pulp_domain:
            if not pulp_domain_enabled:
                raise RuntimeError("Server does not have domains enabled.")
            kwargs["pulp_domain"] = pulp_domain
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(os.urandom(size))
        return gen_object_with_cleanup(artifacts_api_client, temp_file, **kwargs)

    return _random_artifact_factory


@pytest.fixture
def random_artifact(random_artifact_factory):
    return random_artifact_factory()


# Random other fixtures


@pytest.fixture
def delete_orphans_pre(request, orphans_cleanup_api_client, monitor_task):
    if request.node.get_closest_marker("parallel") is not None:
        raise pytest.UsageError("This test is not suitable to be marked parallel.")
    monitor_task(orphans_cleanup_api_client.cleanup({"orphan_protection_time": 0}).task)
    yield


@pytest.fixture(scope="session")
def monitor_task(tasks_api_client, pulp_domain_enabled):
    """
    Wait for a task to reach a final state.

    Returns the task in "completed" state, or throws a `PulpTaskTimeoutError` in case the timeout
    in seconds (defaulting to 30*60) exceeded or a `PulpTaskError` in case it reached any other
    final state.
    """

    def _monitor_task(task_href, timeout=TASK_TIMEOUT):
        task_timeout = int(timeout / SLEEP_TIME)
        for dummy in range(task_timeout):
            try:
                task = tasks_api_client.read(task_href)
            except ApiException as e:
                if pulp_domain_enabled and e.status == 404:
                    # Task's domain has been deleted, nothing to show anymore
                    return {}
                raise e

            if task.state in ["completed", "failed", "canceled", "skipped"]:
                break
            sleep(SLEEP_TIME)
        else:
            raise PulpTaskTimeoutError(task)

        if task.state != "completed":
            raise PulpTaskError(task=task)

        return task

    return _monitor_task


@pytest.fixture(scope="session")
def monitor_task_group(task_groups_api_client):
    """
    Wait for a task group to reach a final state.

    Returns the task group in "completed" state, or throws a `PulpTaskTimeoutError` in case the
    timeout in seconds (defaulting to 30*60) exceeded or a `PulpTaskGroupError` in case it reached
    any other final state.
    """

    def _monitor_task_group(task_group_href, timeout=TASK_TIMEOUT):
        task_timeout = int(timeout / SLEEP_TIME)
        for dummy in range(task_timeout):
            task_group = task_groups_api_client.read(task_group_href)

            if (task_group.waiting + task_group.running + task_group.canceling) == 0:
                break
            sleep(SLEEP_TIME)
        else:
            raise PulpTaskTimeoutError(task_group)

        # If ANYTHING went wrong, throw an error
        if (task_group.failed + task_group.skipped + task_group.canceled) > 0:
            raise PulpTaskGroupError(task_group=task_group)

        return task_group

    return _monitor_task_group


@pytest.fixture(scope="session")
def pulp_settings():
    import django

    django.setup()

    from django.conf import settings

    return settings


@pytest.fixture(scope="session")
def pulp_domain_enabled(pulp_settings):
    return pulp_settings.DOMAIN_ENABLED


@pytest.fixture(scope="session")
def pulp_api_v3_path(pulp_settings, pulp_domain_enabled):
    if pulp_domain_enabled:
        v3_api_root = pulp_settings.V3_DOMAIN_API_ROOT
        v3_api_root = v3_api_root.replace("<slug:pulp_domain>", "default")
    else:
        v3_api_root = pulp_settings.V3_API_ROOT
    if v3_api_root is None:
        raise RuntimeError(
            "This fixture requires the server to have the `V3_API_ROOT` setting set."
        )
    return v3_api_root


@pytest.fixture(scope="session")
def pulp_api_v3_url(bindings_cfg, pulp_api_v3_path):
    return f"{bindings_cfg.host}{pulp_api_v3_path}"


@pytest.fixture(scope="session")
def pulp_content_url(pulp_settings, pulp_domain_enabled):
    url = f"{pulp_settings.CONTENT_ORIGIN}{pulp_settings.CONTENT_PATH_PREFIX}"
    if pulp_domain_enabled:
        url += "default/"
    return url


# Pulp status information fixtures


@pytest.fixture(scope="session")
def pulp_status(status_api_client):
    return status_api_client.status_read()


@pytest.fixture(scope="session")
def pulp_versions(pulp_status):
    """A dictionary containing pulp plugin versions."""
    return {item.component: parse_version(item.version) for item in pulp_status.versions}


@pytest.fixture
def needs_pulp_plugin(pulp_versions):
    """Skip test if a component is not available in the specified version range"""

    def _needs_pulp_plugin(plugin, min=None, max=None):
        if plugin not in pulp_versions:
            pytest.skip(f"Plugin {plugin} is not installed.")
        if min is not None and pulp_versions[plugin] < parse_version(min):
            pytest.skip(f"Plugin {plugin} too old (<{min}).")
        if max is not None and pulp_versions[plugin] >= parse_version(max):
            pytest.skip(f"Plugin {plugin} too new (>={max}).")

    return _needs_pulp_plugin


@pytest.fixture
def has_pulp_plugin(pulp_versions):
    def _has_pulp_plugin(plugin, min=None, max=None):
        if plugin not in pulp_versions:
            return False
        if min is not None and pulp_versions[plugin] < parse_version(min):
            return False
        if max is not None and pulp_versions[plugin] >= parse_version(max):
            return False
        return True

    return _has_pulp_plugin


@pytest.fixture(scope="session")
def redis_status(pulp_status):
    """A boolean value which tells whether the connection to redis was established or not."""
    return pulp_status.redis_connection.connected


# Object Cleanup fixtures


@pytest.fixture(scope="class")
def add_to_cleanup(monitor_task):
    """Fixture to allow pulp objects to be deleted in reverse order after the test module."""
    obj_refs = []

    def _add_to_cleanup(api_client, pulp_href):
        obj_refs.append((api_client, pulp_href))

    yield _add_to_cleanup

    delete_task_hrefs = []
    # Delete newest items first to avoid dependency lockups
    for api_client, pulp_href in reversed(obj_refs):
        try:
            task_url = api_client.delete(pulp_href).task
            delete_task_hrefs.append(task_url)
        except Exception:
            # There was no delete task for this unit or the unit may already have been deleted.
            # Also we can never be sure which one is the right ApiException to catch.
            pass

    for deleted_task_href in delete_task_hrefs:
        with suppress(ApiException):
            # The task itself may be gone at this point (e.g. by being part of a deleted domain).
            monitor_task(deleted_task_href)


@pytest.fixture(scope="class")
def gen_object_with_cleanup(add_to_cleanup, monitor_task):
    def _gen_object_with_cleanup(api_client, *args, **kwargs):
        new_obj = api_client.create(*args, **kwargs)
        try:
            add_to_cleanup(api_client, new_obj.pulp_href)
        except AttributeError:
            # This is a task and the real object href comes from monitoring it
            task_data = monitor_task(new_obj.task)

            for created_resource in task_data.created_resources:
                try:
                    new_obj = api_client.read(created_resource)
                except Exception:
                    pass  # This isn't the right created_resource for this api_client
                else:
                    add_to_cleanup(api_client, new_obj.pulp_href)
                    return new_obj

            msg = f"No appropriate created_resource could be found in task data {task_data}"
            raise TypeError(msg)

        return new_obj

    return _gen_object_with_cleanup


@pytest.fixture(scope="class")
def add_to_filesystem_cleanup():
    obj_paths = []

    def _add_to_filesystem_cleanup(path):
        obj_paths.append(path)

    yield _add_to_filesystem_cleanup

    for path in reversed(obj_paths):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                # the file may no longer exist, but we do not care
                pass


@pytest.fixture(scope="session")
def download_content_unit(bindings_cfg, pulp_domain_enabled):
    def _download_content_unit(base_path, content_path, domain="default"):
        async def _get_response(url):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.read()

        if pulp_domain_enabled:
            url_fragments = [
                bindings_cfg.host,
                "pulp/content",
                domain,
                base_path,
                content_path,
            ]
        else:
            url_fragments = [
                bindings_cfg.host,
                "pulp/content",
                base_path,
                content_path,
            ]
        url = "/".join(url_fragments)
        return asyncio.run(_get_response(url))

    return _download_content_unit


@pytest.fixture(scope="session")
def http_get():
    def _http_get(url, **kwargs):
        async def _send_request():
            async with aiohttp.ClientSession(raise_for_status=True) as session:
                async with session.get(url, **kwargs) as response:
                    return await response.content.read()

        response = asyncio.run(_send_request())
        return response

    return _http_get


@pytest.fixture
def wget_recursive_download_on_host():
    def _wget_recursive_download_on_host(url, destination):
        subprocess.check_output(
            [
                "wget",
                "--recursive",
                "--no-parent",
                "--no-host-directories",
                "--directory-prefix",
                destination,
                url,
            ]
        )

    return _wget_recursive_download_on_host


@pytest.fixture()
def domain_factory(domains_api_client, pulp_settings, gen_object_with_cleanup):
    def _domain_factory():
        if not pulp_settings.DOMAIN_ENABLED:
            pytest.skip("Domains not enabled")
        keys = dict()
        keys["pulpcore.app.models.storage.FileSystem"] = ["MEDIA_ROOT"]
        keys["storages.backends.s3boto3.S3Boto3Storage"] = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_S3_ENDPOINT_URL",
            "AWS_S3_ADDRESSING_STYLE",
            "AWS_S3_SIGNATURE_VERSION",
            "AWS_S3_REGION_NAME",
            "AWS_STORAGE_BUCKET_NAME",
        ]
        keys["storages.backends.azure_storage.AzureStorage"] = [
            "AZURE_ACCOUNT_NAME",
            "AZURE_CONTAINER",
            "AZURE_ACCOUNT_KEY",
            "AZURE_URL_EXPIRATION_SECS",
            "AZURE_OVERWRITE_FILES",
            "AZURE_LOCATION",
            "AZURE_CONNECTION_STRING",
        ]
        settings = dict()
        for key in keys[pulp_settings.DEFAULT_FILE_STORAGE]:
            settings[key] = getattr(pulp_settings, key, None)
        body = {
            "name": str(uuid.uuid4()),
            "storage_class": pulp_settings.DEFAULT_FILE_STORAGE,
            "storage_settings": settings,
        }
        return gen_object_with_cleanup(domains_api_client, body)

    return _domain_factory
