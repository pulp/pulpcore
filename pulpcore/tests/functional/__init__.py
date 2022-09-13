import trustme
import urllib3
import time
import socket
import ssl
import asyncio
import threading
import uuid
import proxy

import pytest

from aiohttp import web
from yarl import URL

from pulpcore.tests.suite import cli
from pulpcore.tests.suite.config import get_config
from pulpcore.tests.suite.bindings import delete_orphans, monitor_task
from pulpcore.tests.suite.utils import get_pulp_setting
from pulpcore.client.pulpcore.exceptions import ApiException

from pulpcore.client.pulpcore import (
    ApiClient,
    ArtifactsApi,
    ContentApi,
    ContentguardsApi,
    ContentguardsRbacApi,
    ContentguardsContentRedirectApi,
    DistributionsApi,
    ExportersPulpApi,
    ExportersPulpExportsApi,
    GroupsApi,
    GroupsRolesApi,
    GroupsUsersApi,
    ImportersPulpApi,
    ImportersPulpImportsApi,
    OrphansCleanupApi,
    PublicationsApi,
    RemotesApi,
    RepositoriesApi,
    RolesApi,
    SigningServicesApi,
    StatusApi,
    TasksApi,
    TaskSchedulesApi,
    UploadsApi,
    UsersApi,
    UsersRolesApi,
)

from .gpg_ascii_armor_signing_service import (  # noqa: F401
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

PULP_SERVICES = ("pulpcore-content", "pulpcore-api", "pulpcore-worker@1", "pulpcore-worker@2")


def pytest_addoption(parser):
    group = parser.getgroup("pulp-smash")
    group.addoption(
        "--pulp-no-leftovers",
        action="store_true",
        dest="pulp_no_leftovers",
        default=False,
        help="Enable this to have Pulp plugins check for objects leftover by tests.",
    )
    group.addoption(
        "--nightly",
        action="store_true",
        default=False,
        help="Enable to run nightly test.",
    )


def pytest_addhooks(pluginmanager):
    """Add the hooks that pulp-smash provides from the 'newhooks' module."""
    from pulpcore.tests.suite import pulphooks

    pluginmanager.add_hookspecs(pulphooks)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):

    yield  # We need the real pytest_runtest_teardown to run

    if item.config.getoption("--pulp-no-leftovers"):
        item.config.hook.pytest_check_for_leftover_pulp_objects(config=item.config)


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


# pytest configuration


def pytest_configure(config):
    if (
        config.getoption("--pulp-no-leftovers")
        and config.pluginmanager.hasplugin("xdist")
        and config.getoption("-n")
    ):
        raise Exception("The --pulp-no-leftovers cannot be used with -n from xdist")

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
        "from_pulpcore_for_all_plugins: marks tests from pulpcore as beneficial for plugins to run",
    )
    config.addinivalue_line(
        "markers",
        "nightly: marks tests as intended to run during the nightly CI run",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_check_for_leftover_pulp_objects(config):
    cfg = get_config()
    pulpcore_client = ApiClient(cfg.get_bindings_config())
    tasks_api_client = TasksApi(pulpcore_client)

    for task in tasks_api_client.list().results:
        if task.state in ["running", "waiting"]:
            raise Exception("This test left over a task in the running or waiting state.")

    apis_to_check = [
        ContentguardsApi(pulpcore_client),
        DistributionsApi(pulpcore_client),
        PublicationsApi(pulpcore_client),
        RemotesApi(pulpcore_client),
        RepositoriesApi(pulpcore_client),
    ]
    for api_to_check in apis_to_check:
        if api_to_check.list().count > 0:
            raise Exception(f"This test left over a {api_to_check}.")


# Threaded local fixture servers


class ThreadedAiohttpServer(threading.Thread):
    def __init__(self, shutdown_event, app, host, port, ssl_ctx):
        super().__init__()
        self.shutdown_event = shutdown_event
        self.app = app
        self.host = host
        self.port = port
        self.ssl_ctx = ssl_ctx

    def run(self):
        loop = asyncio.new_event_loop()
        runner = web.AppRunner(self.app)
        asyncio.set_event_loop(loop)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, host=self.host, port=self.port, ssl_context=self.ssl_ctx)
        loop.run_until_complete(site.start())
        while True:
            loop.run_until_complete(asyncio.sleep(1))
            if self.shutdown_event.is_set():
                break


class ThreadedAiohttpServerData:
    def __init__(
        self,
        host,
        port,
        shutdown_event,
        thread,
        ssl_ctx,
        requests_record,
    ):
        self.host = host
        self.port = port
        self.shutdown_event = shutdown_event
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


# Webserver Fixtures


@pytest.fixture
def unused_port():
    def _unused_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    return _unused_port


@pytest.fixture
def gen_threaded_aiohttp_server(pulp_cfg, unused_port):
    fixture_servers_data = []

    def _gen_threaded_aiohttp_server(app, ssl_ctx, call_record):
        host = pulp_cfg.aiohttp_fixtures_origin
        port = unused_port()
        shutdown_event = threading.Event()
        fixture_server = ThreadedAiohttpServer(shutdown_event, app, host, port, ssl_ctx)
        fixture_server.daemon = True
        fixture_server.start()
        fixture_server_data = ThreadedAiohttpServerData(
            host=host,
            port=port,
            shutdown_event=shutdown_event,
            thread=fixture_server,
            requests_record=call_record,
            ssl_ctx=ssl_ctx,
        )
        fixture_servers_data.append(fixture_server_data)
        return fixture_server_data

    yield _gen_threaded_aiohttp_server

    for fixture_server_data in fixture_servers_data:
        fixture_server_data.shutdown_event.set()

    for fixture_server_data in fixture_servers_data:
        fixture_server_data.thread.join()


def add_file_system_route(app, fixtures_root):
    new_routes = [web.static("/", fixtures_root.absolute(), show_index=True)]
    app.add_routes(new_routes)


def add_recording_route(app, fixtures_root):
    requests = []

    async def all_requests_handler(request):
        requests.append(request)
        path = fixtures_root / request.raw_path[1:]  # Strip off leading '/'
        if path.is_file():
            return web.FileResponse(path)
        else:
            raise web.HTTPNotFound()

    app.add_routes([web.get("/{tail:.*}", all_requests_handler)])

    return requests


@pytest.fixture
def gen_fixture_server(gen_threaded_aiohttp_server):
    def _gen_fixture_server(fixtures_root, ssl_ctx):
        app = web.Application()
        call_record = add_recording_route(app, fixtures_root)
        return gen_threaded_aiohttp_server(app, ssl_ctx, call_record)

    yield _gen_fixture_server


# Proxy Fixtures


@pytest.fixture
def http_proxy(pulp_cfg, unused_port):
    host = pulp_cfg.aiohttp_fixtures_origin
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
def http_proxy_with_auth(pulp_cfg, unused_port):
    host = pulp_cfg.aiohttp_fixtures_origin
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
def https_proxy(pulp_cfg, unused_port, proxy_tls_certificate_pem_path):
    host = pulp_cfg.aiohttp_fixtures_origin
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


# Infrastructure Fixtures


@pytest.fixture(scope="session")
def pulp_cfg():
    return get_config()


@pytest.fixture(scope="session")
def bindings_cfg(pulp_cfg):
    return pulp_cfg.get_bindings_config()


@pytest.fixture(scope="session")
def cli_client(pulp_cfg):
    return cli.Client(pulp_cfg)


@pytest.fixture(scope="session")
def svc_mgr(pulp_cfg):
    PULP_HOST = pulp_cfg.hosts[0]
    return cli.ServiceManager(pulp_cfg, PULP_HOST)


@pytest.fixture
def stop_and_check_services(status_api_client, svc_mgr):
    """Stop services and wait up to 30 seconds to check if services have stopped."""

    def _stop_and_check_services(pulp_services=None):
        svc_mgr.stop(pulp_services or PULP_SERVICES)
        for i in range(10):
            time.sleep(3)
            try:
                status_api_client.status_read()
            except (urllib3.exceptions.MaxRetryError, ApiException):
                return True
        return False

    yield _stop_and_check_services


@pytest.fixture
def start_and_check_services(status_api_client, svc_mgr):
    """Start services and wait up to 30 seconds to check if services have started."""

    def _start_and_check_services(pulp_services=None):
        svc_mgr.start(pulp_services or PULP_SERVICES)
        for i in range(10):
            time.sleep(3)
            try:
                status, http_code, _ = status_api_client.status_read_with_http_info()
            except (urllib3.exceptions.MaxRetryError, ApiException):
                # API is not responding
                continue
            else:
                if (
                    http_code == 200
                    and len(status.online_workers) > 0
                    and len(status.online_content_apps) > 0
                    and status.database_connection.connected
                ):
                    return True
                else:
                    # sometimes it takes longer for the content app to start
                    continue
        return False

    yield _start_and_check_services


# Server Side TLS Fixtures


@pytest.fixture(scope="session")
def tls_certificate_authority():
    return trustme.CA()


@pytest.fixture
def tls_certificate_authority_cert(tls_certificate_authority):
    return tls_certificate_authority.cert_pem.bytes().decode()


@pytest.fixture
def tls_certificate(pulp_cfg, tls_certificate_authority):
    return tls_certificate_authority.issue_cert(
        pulp_cfg.aiohttp_fixtures_origin,
    )


# Proxy TLS Fixtures


@pytest.fixture(scope="session")
def proxy_tls_certificate_authority():
    return trustme.CA()


@pytest.fixture
def proxy_tls_certificate(pulp_cfg, client_tls_certificate_authority):
    return client_tls_certificate_authority.issue_cert(
        pulp_cfg.aiohttp_fixtures_origin,
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
def client_tls_certificate(pulp_cfg, client_tls_certificate_authority):
    return client_tls_certificate_authority.issue_cert(
        pulp_cfg.aiohttp_fixtures_origin,
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


# Object Cleanup fixtures


@pytest.fixture
def add_to_cleanup():
    """Fixture to allow pulp objects to be deleted in reverse order after the test."""
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
        monitor_task(deleted_task_href)


@pytest.fixture
def gen_object_with_cleanup(add_to_cleanup):
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


@pytest.fixture
def cid():
    value = str(uuid.uuid4())
    yield value
    print(f"Correlation-ID = {value}")


@pytest.fixture
def pulpcore_client(cid, bindings_cfg):
    api_client = ApiClient(bindings_cfg)
    api_client.default_headers["Correlation-ID"] = cid
    return api_client


@pytest.fixture
def tasks_api_client(pulpcore_client):
    return TasksApi(pulpcore_client)


@pytest.fixture
def artifacts_api_client(pulpcore_client):
    return ArtifactsApi(pulpcore_client)


@pytest.fixture
def uploads_api_client(pulpcore_client):
    return UploadsApi(pulpcore_client)


@pytest.fixture
def task_schedules_api_client(pulpcore_client):
    return TaskSchedulesApi(pulpcore_client)


@pytest.fixture
def status_api_client(pulpcore_client):
    return StatusApi(pulpcore_client)


@pytest.fixture
def groups_api_client(pulpcore_client):
    return GroupsApi(pulpcore_client)


@pytest.fixture
def groups_users_api_client(pulpcore_client):
    return GroupsUsersApi(pulpcore_client)


@pytest.fixture
def groups_roles_api_client(pulpcore_client):
    return GroupsRolesApi(pulpcore_client)


@pytest.fixture
def users_api_client(pulpcore_client):
    return UsersApi(pulpcore_client)


@pytest.fixture
def users_roles_api_client(pulpcore_client):
    return UsersRolesApi(pulpcore_client)


@pytest.fixture
def roles_api_client(pulpcore_client):
    "Provies the pulp core Roles API client object."
    return RolesApi(pulpcore_client)


@pytest.fixture
def content_api_client(pulpcore_client):
    return ContentApi(pulpcore_client)


@pytest.fixture
def distributions_api_client(pulpcore_client):
    return DistributionsApi(pulpcore_client)


@pytest.fixture
def remotes_api_client(pulpcore_client):
    return RemotesApi(pulpcore_client)


@pytest.fixture
def repositories_api_client(pulpcore_client):
    return RepositoriesApi(pulpcore_client)


@pytest.fixture
def publications_api_client(pulpcore_client):
    return PublicationsApi(pulpcore_client)


@pytest.fixture
def exporters_pulp_api_client(pulpcore_client):
    return ExportersPulpApi(pulpcore_client)


@pytest.fixture
def exporters_pulp_exports_api_client(pulpcore_client):
    return ExportersPulpExportsApi(pulpcore_client)


@pytest.fixture
def importers_pulp_api_client(pulpcore_client):
    return ImportersPulpApi(pulpcore_client)


@pytest.fixture
def importers_pulp_imports_api_client(pulpcore_client):
    return ImportersPulpImportsApi(pulpcore_client)


@pytest.fixture
def signing_service_api_client(pulpcore_client):
    return SigningServicesApi(pulpcore_client)


@pytest.fixture
def content_guards_api_client(pulpcore_client):
    return ContentguardsApi(pulpcore_client)


@pytest.fixture
def rbac_contentguard_api_client(pulpcore_client):
    return ContentguardsRbacApi(pulpcore_client)


@pytest.fixture
def redirect_contentguard_api_client(pulpcore_client):
    return ContentguardsContentRedirectApi(pulpcore_client)


@pytest.fixture
def orphans_cleanup_api_client(pulpcore_client):
    return OrphansCleanupApi(pulpcore_client)


@pytest.fixture
def role_factory(roles_api_client, gen_object_with_cleanup):
    def _role_factory(**kwargs):
        return gen_object_with_cleanup(roles_api_client, kwargs)

    return _role_factory


@pytest.fixture
def gen_user(bindings_cfg, users_api_client, users_roles_api_client, gen_object_with_cleanup):
    class user_context:
        def __init__(self, username=None, model_roles=None, object_roles=None):
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
                        user_role={"role": role, "content_object": None},
                    )
            if object_roles:
                for role, content_object in object_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "content_object": content_object},
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
def delete_orphans_pre(request):
    if request.node.get_closest_marker("parallel") is not None:
        raise pytest.UsageError("This test is not suitable to be marked parallel.")
    delete_orphans()
    yield


@pytest.fixture(scope="session")
def pulp_api_v3_path(cli_client):
    v3_api_root = get_pulp_setting(cli_client, "V3_API_ROOT")
    if v3_api_root is None:
        raise RuntimeError(
            "This fixture requires the server to have the `V3_API_ROOT` setting set."
        )
    return v3_api_root


@pytest.fixture(scope="session")
def pulp_api_v3_url(pulp_cfg, pulp_api_v3_path):
    return f"{pulp_cfg.get_base_url()}{pulp_api_v3_path}"


@pytest.fixture
def random_artifact(random_artifact_factory):
    return random_artifact_factory()


@pytest.fixture
def random_artifact_factory(artifacts_api_client, tmp_path, gen_object_with_cleanup):
    def _random_artifact_factory():
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(uuid.uuid4().bytes)
        return gen_object_with_cleanup(artifacts_api_client, temp_file)

    return _random_artifact_factory
