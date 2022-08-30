import uuid

import pytest

from pulp_smash.config import get_config
from pulp_smash.pulp3.bindings import delete_orphans
from pulp_smash.utils import get_pulp_setting

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


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "from_pulpcore_for_all_plugins: marks tests from pulpcore as beneficial for plugins to run",
    )


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
