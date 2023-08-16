import aiohttp
import asyncio
import gnupg
import json
import os
import requests
import shutil
import socket
import ssl
import subprocess
import threading
import uuid

import pytest

from aiohttp import web
from contextlib import suppress
from dataclasses import dataclass
from packaging.version import parse as parse_version
from time import sleep
from yarl import URL

from pulpcore.tests.functional.utils import (
    SLEEP_TIME,
    TASK_TIMEOUT,
    BindingsNamespace,
    PulpTaskError,
    PulpTaskGroupError,
    add_recording_route,
)


try:
    import pulp_smash  # noqa: F401
except ImportError:

    def pytest_addoption(parser):
        group = parser.getgroup("pulpcore")
        group.addoption(
            "--nightly",
            action="store_true",
            default=False,
            help="Enable to run nightly test.",
        )

    def pytest_collection_modifyitems(config, items):
        # Skip nightly tests by default
        # https://docs.pytest.org/en/7.1.x/example/simple.html#control-skipping-of-tests-according-to-command-line-option
        if config.getoption("--nightly"):
            # Run all tests unmodified
            return
        skip_nightly = pytest.mark.skip(reason="need --nightly option to run")
        for item in items:
            if "nightly" in item.keywords:
                item.add_marker(skip_nightly)


class PulpTaskTimeoutError(Exception):
    """Exception to describe task and taskgroup timeout errors."""

    def __init__(self, awaitable):
        super().__init__(self, f"Timeout: {awaitable}")
        self.awaitable = awaitable


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


# API Bindings fixtures


@pytest.fixture(scope="session")
def bindings_cfg():
    from pulpcore.client.pulpcore import Configuration

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
def pulpcore_bindings(_api_client_set, bindings_cfg):
    """
    A namespace providing preconfigured pulpcore api clients.

    e.g. `pulpcore_bindings.WorkersApi.list()`.
    """
    from pulpcore.client import pulpcore as pulpcore_bindings_module

    pulpcore_client = pulpcore_bindings_module.ApiClient(bindings_cfg)
    _api_client_set.add(pulpcore_client)
    yield BindingsNamespace(pulpcore_bindings_module, pulpcore_client)
    _api_client_set.remove(pulpcore_client)


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
        await self.shutdown_event.wait()
        await runner.cleanup()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.shutdown_event = asyncio.Event()
        self.loop.run_until_complete(self.arun())

    async def astop(self):
        self.shutdown_event.set()

    def stop(self):
        fut = asyncio.run_coroutine_threadsafe(self.astop(), self.loop)
        fut.result()


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

    def _received_otel_span(data, retries=3):
        if os.environ.get("PULP_OTEL_ENABLED") != "true":
            # pretend everything is working as expected if tests are run from
            # a non-configured runner
            return True

        async def _send_request():
            async with aiohttp.ClientSession(raise_for_status=False) as session:
                otel_server_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                async with session.post(f"{otel_server_url}/test", json=data) as response:
                    return response.status

        while retries:
            status = asyncio.run(_send_request())
            if status == 200:
                return True
            sleep(2)
            retries -= 1
        return False

    return _received_otel_span


@pytest.fixture(scope="session")
def received_otel_metrics():
    """A fixture for checking the presence of specific metrics on the otel collector server.

    Ensure the collector server is up and running before executing tests with this fixture. To do
    so, please, run the server as follows: python3 pulpcore/tests/functional/assets/otel_server.py
    """

    def _received_otel_metric(data, retries=3):
        if os.environ.get("PULP_OTEL_ENABLED") != "true":
            # pretend everything is working as expected if tests are run from
            # a non-configured runner
            return True

        async def _send_request():
            async with aiohttp.ClientSession(raise_for_status=False) as session:
                otel_server_url = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
                async with session.post(f"{otel_server_url}/metrics_test", json=data) as response:
                    return response.status

        while retries:
            status = asyncio.run(_send_request())
            if status == 200:
                return True
            sleep(2)
            retries -= 1
        return False

    return _received_otel_metric


@pytest.fixture
def test_path():
    return os.getenv("PYTEST_CURRENT_TEST").split()[0]


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


@pytest.fixture(scope="session")
def _proxy_module():
    import proxy

    return proxy


@pytest.fixture
def http_proxy(_proxy_module, fixtures_cfg, unused_port):
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

    with _proxy_module.Proxy(input_args=proxypy_args):
        yield proxy_data


@pytest.fixture
def http_proxy_with_auth(_proxy_module, fixtures_cfg, unused_port):
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

    with _proxy_module.Proxy(input_args=proxypy_args):
        yield proxy_data


@pytest.fixture
def https_proxy(_proxy_module, fixtures_cfg, unused_port, proxy_tls_certificate_pem_path):
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

    with _proxy_module.Proxy(input_args=proxypy_args):
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
def _trustme_module():
    import trustme

    return trustme


@pytest.fixture(scope="session")
def tls_certificate_authority(_trustme_module):
    return _trustme_module.CA()


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
def proxy_tls_certificate_authority(_trustme_module):
    return _trustme_module.CA()


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
def client_tls_certificate_authority(_trustme_module):
    return _trustme_module.CA()


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
def role_factory(pulpcore_bindings, gen_object_with_cleanup):
    def _role_factory(**kwargs):
        return gen_object_with_cleanup(pulpcore_bindings.RolesApi, kwargs)

    return _role_factory


@pytest.fixture
def gen_user(bindings_cfg, pulpcore_bindings, gen_object_with_cleanup):
    class user_context:
        def __init__(self, username=None, model_roles=None, object_roles=None, domain_roles=None):
            self.username = username or str(uuid.uuid4())
            self.password = str(uuid.uuid4())
            self.user = gen_object_with_cleanup(
                pulpcore_bindings.UsersApi, {"username": self.username, "password": self.password}
            )
            self._saved_credentials = []

            if model_roles:
                for role in model_roles:
                    pulpcore_bindings.UsersRolesApi.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "domain": None, "content_object": None},
                    )
            if domain_roles:
                for role, domain in domain_roles:
                    pulpcore_bindings.UsersRolesApi.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "domain": domain, "content_object": None},
                    )
            if object_roles:
                for role, content_object in object_roles:
                    pulpcore_bindings.UsersRolesApi.create(
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
def random_artifact_factory(pulpcore_bindings, tmp_path, pulp_domain_enabled):
    def _random_artifact_factory(size=32, pulp_domain=None):
        kwargs = {}
        if pulp_domain:
            if not pulp_domain_enabled:
                raise RuntimeError("Server does not have domains enabled.")
            kwargs["pulp_domain"] = pulp_domain
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(os.urandom(size))
        return pulpcore_bindings.ArtifactsApi.create(temp_file, **kwargs)

    return _random_artifact_factory


@pytest.fixture
def random_artifact(random_artifact_factory):
    return random_artifact_factory()


@pytest.fixture
def backend_settings_factory(pulp_settings):
    def _settings_factory(storage_class=None, storage_settings=None):
        if not pulp_settings.DOMAIN_ENABLED:
            pytest.skip("Domains not enabled")
        keys = dict()
        keys["pulpcore.app.models.storage.FileSystem"] = ["MEDIA_ROOT", "MEDIA_URL"]
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
        settings = storage_settings or dict()
        backend = storage_class or pulp_settings.DEFAULT_FILE_STORAGE
        for key in keys[backend]:
            if key not in settings:
                settings[key] = getattr(pulp_settings, key, None)
        return backend, settings

    return _settings_factory


@pytest.fixture()
def domain_factory(
    pulpcore_bindings, pulp_domain_enabled, backend_settings_factory, gen_object_with_cleanup
):
    def _domain_factory(**kwargs):
        if not pulp_domain_enabled:
            pytest.skip("Domains not enabled")

        storage_class, storage_settings = backend_settings_factory(
            storage_class=kwargs.pop("storage_class", None),
            storage_settings=kwargs.pop("storage_settings", None),
        )
        kwargs.setdefault("name", str(uuid.uuid4()))
        kwargs.update({"storage_class": storage_class, "storage_settings": storage_settings})
        return gen_object_with_cleanup(pulpcore_bindings.DomainsApi, kwargs)

    return _domain_factory


# Random other fixtures


@pytest.fixture
def delete_orphans_pre(request, pulpcore_bindings, monitor_task):
    if request.node.get_closest_marker("parallel") is not None:
        raise pytest.UsageError("This test is not suitable to be marked parallel.")
    monitor_task(pulpcore_bindings.OrphansCleanupApi.cleanup({"orphan_protection_time": 0}).task)
    yield


@pytest.fixture(scope="session")
def monitor_task(pulpcore_bindings, pulp_domain_enabled):
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
                task = pulpcore_bindings.TasksApi.read(task_href)
            except pulpcore_bindings.ApiException as e:
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
def monitor_task_group(pulpcore_bindings):
    """
    Wait for a task group to reach a final state.

    Returns the task group in "completed" state, or throws a `PulpTaskTimeoutError` in case the
    timeout in seconds (defaulting to 30*60) exceeded or a `PulpTaskGroupError` in case it reached
    any other final state.
    """

    def _monitor_task_group(task_group_href, timeout=TASK_TIMEOUT):
        task_timeout = int(timeout / SLEEP_TIME)
        for dummy in range(task_timeout):
            task_group = pulpcore_bindings.TaskGroupsApi.read(task_group_href)

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
def pulp_content_origin(pulp_settings):
    return pulp_settings.CONTENT_ORIGIN


@pytest.fixture(scope="session")
def pulp_content_origin_with_prefix(pulp_settings):
    return pulp_settings.CONTENT_ORIGIN + pulp_settings.CONTENT_PATH_PREFIX[:-1]


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
def pulp_status(pulpcore_bindings):
    return pulpcore_bindings.StatusApi.status_read()


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
        with suppress(Exception):
            # There was no delete task for this unit or the unit may already have been deleted.
            # Also we can never be sure which one is the right ApiException to catch.
            task_url = api_client.delete(pulp_href).task
            delete_task_hrefs.append(task_url)

    for deleted_task_href in delete_task_hrefs:
        with suppress(Exception):
            # The task itself may be gone at this point (e.g. by being part of a deleted domain).
            # Also we can never be sure which one is the right ApiException to catch.
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
def download_content_unit(pulp_domain_enabled, pulp_content_origin_with_prefix):
    def _download_content_unit(base_path, content_path, domain="default"):
        async def _get_response(url):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.read()

        if pulp_domain_enabled:
            url_fragments = [
                pulp_content_origin_with_prefix,
                domain,
                base_path,
                content_path,
            ]
        else:
            url_fragments = [
                pulp_content_origin_with_prefix,
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


# Tasking related fixtures


@pytest.fixture(scope="session")
def dispatch_task(pulpcore_bindings):
    def _dispatch_task(*args, task_group_id=None, **kwargs):
        cid = pulpcore_bindings.client.default_headers.get("Correlation-ID") or str(uuid.uuid4())
        username = pulpcore_bindings.client.configuration.username
        commands = (
            "from django_guid import set_guid; "
            "from pulpcore.tasking.tasks import dispatch; "
            "from pulpcore.app.models import TaskGroup; "
            "from pulpcore.app.util import get_url, set_current_user; "
            "from django.contrib.auth import get_user_model; "
            "User = get_user_model(); "
            f"user = User.objects.filter(username='{username}').first(); "
            "set_current_user(user); "
            f"set_guid({cid!r}); "
            f"tg = {task_group_id!r} and TaskGroup.objects.filter(pk={task_group_id!r}).first(); "
            f"task = dispatch(*{args!r}, task_group=tg, **{kwargs!r}); "
            "print(get_url(task))"
        )

        process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)

        assert process.returncode == 0
        task_href = process.stdout.decode().strip()
        return task_href

    return _dispatch_task


@pytest.fixture(scope="session")
def dispatch_task_group(dispatch_task):
    def _dispatch_task_group(task_name, *args, **kwargs):
        commands = (
            "from pulpcore.app.models import TaskGroup; "
            "from pulpcore.app.util import get_url; "
            "task_group = TaskGroup.objects.create(); "
            "print(task_group.pk, get_url(task_group))"
        )
        process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)
        assert process.returncode == 0
        tgroup_id, tgroup_href = process.stdout.decode().strip().split()

        dispatch_task(task_name, *args, task_group_id=tgroup_id, **kwargs)
        return tgroup_href

    return _dispatch_task_group


# GPG related fixtures


SIGNING_SCRIPT_STRING = r"""#!/usr/bin/env bash

FILE_PATH=$1
SIGNATURE_PATH="$1.asc"

GPG_KEY_ID="pulp-fixture-signing-key"

# Create a detached signature
gpg --quiet --batch --homedir HOMEDIRHERE --detach-sign --local-user "${GPG_KEY_ID}" \
   --armor --output ${SIGNATURE_PATH} ${FILE_PATH}

# Check the exit status
STATUS=$?
if [[ ${STATUS} -eq 0 ]]; then
   echo {\"file\": \"${FILE_PATH}\", \"signature\": \"${SIGNATURE_PATH}\"}
else
   exit ${STATUS}
fi
"""


@pytest.fixture(scope="session")
def signing_script_path(signing_script_temp_dir, signing_gpg_homedir_path):
    signing_script_file = signing_script_temp_dir / "sign-metadata.sh"
    signing_script_file.write_text(
        SIGNING_SCRIPT_STRING.replace("HOMEDIRHERE", str(signing_gpg_homedir_path))
    )

    signing_script_file.chmod(0o755)

    return signing_script_file


@pytest.fixture(scope="session")
def signing_script_temp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("sigining_script_dir")


@pytest.fixture(scope="session")
def signing_gpg_homedir_path(tmp_path_factory):
    return tmp_path_factory.mktemp("gpghome")


@pytest.fixture
def sign_with_ascii_armored_detached_signing_service(signing_script_path, signing_gpg_metadata):
    """
    Runs the test signing script manually, locally, and returns the signature file produced.
    """

    def _sign_with_ascii_armored_detached_signing_service(filename):
        env = {"PULP_SIGNING_KEY_FINGERPRINT": signing_gpg_metadata[1]}
        cmd = (signing_script_path, filename)
        completed_process = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if completed_process.returncode != 0:
            raise RuntimeError(str(completed_process.stderr))

        try:
            return_value = json.loads(completed_process.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("The signing script did not return valid JSON!")

        return return_value

    return _sign_with_ascii_armored_detached_signing_service


@pytest.fixture(scope="session")
def signing_gpg_metadata(signing_gpg_homedir_path):
    """A fixture that returns a GPG instance and related metadata (i.e., fingerprint, keyid)."""
    PRIVATE_KEY_URL = "https://raw.githubusercontent.com/pulp/pulp-fixtures/master/common/GPG-PRIVATE-KEY-fixture-signing"  # noqa: E501

    response = requests.get(PRIVATE_KEY_URL)
    response.raise_for_status()

    gpg = gnupg.GPG(gnupghome=signing_gpg_homedir_path)
    gpg.import_keys(response.content)

    fingerprint = gpg.list_keys()[0]["fingerprint"]
    keyid = gpg.list_keys()[0]["keyid"]

    gpg.trust_keys(fingerprint, "TRUST_ULTIMATE")

    return gpg, fingerprint, keyid


@pytest.fixture(scope="session")
def pulp_trusted_public_key(signing_gpg_metadata):
    """Fixture to extract the ascii armored trusted public test key."""
    gpg, _, keyid = signing_gpg_metadata
    return gpg.export_keys([keyid])


@pytest.fixture(scope="session")
def pulp_trusted_public_key_fingerprint(signing_gpg_metadata):
    """Fixture to extract the ascii armored trusted public test keys fingerprint."""
    return signing_gpg_metadata[1]


@pytest.fixture(scope="session")
def _ascii_armored_detached_signing_service_name(
    bindings_cfg,
    signing_script_path,
    signing_gpg_metadata,
    signing_gpg_homedir_path,
    pytestconfig,
):
    service_name = str(uuid.uuid4())
    gpg, fingerprint, keyid = signing_gpg_metadata

    cmd = (
        "pulpcore-manager",
        "add-signing-service",
        service_name,
        str(signing_script_path),
        fingerprint,
        "--class",
        "core:AsciiArmoredDetachedSigningService",
        "--gnupghome",
        str(signing_gpg_homedir_path),
    )
    completed_process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed_process.returncode == 0

    yield service_name

    cmd = (
        "pulpcore-manager",
        "remove-signing-service",
        service_name,
        "--class",
        "core:AsciiArmoredDetachedSigningService",
    )
    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def ascii_armored_detached_signing_service(
    _ascii_armored_detached_signing_service_name, pulpcore_bindings
):
    return pulpcore_bindings.SigningServicesApi.list(
        name=_ascii_armored_detached_signing_service_name
    ).results[0]
