import uuid

import pytest

from pulp_smash.config import get_config
from pulp_smash.pulp3.bindings import delete_orphans
from pulp_smash.utils import get_pulp_setting


from pulpcore.client.pulpcore import (
    ApiClient,
    ContentguardsApi,
    DistributionsApi,
    PublicationsApi,
    RepositoriesApi,
    SigningServicesApi,
    StatusApi,
    TasksApi,
    TaskSchedulesApi,
    UsersApi,
    UsersRolesApi,
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
        RepositoriesApi(pulpcore_client),
    ]
    for api_to_check in apis_to_check:
        if api_to_check.list().count > 0:
            raise Exception(f"This test left over a {api_to_check}.")


@pytest.fixture(scope="session")
def pulpcore_client(bindings_cfg):
    return ApiClient(bindings_cfg)


@pytest.fixture(scope="session")
def tasks_api_client(pulpcore_client):
    return TasksApi(pulpcore_client)


@pytest.fixture(scope="session")
def task_schedules_api_client(pulpcore_client):
    return TaskSchedulesApi(pulpcore_client)


@pytest.fixture(scope="session")
def status_api_client(pulpcore_client):
    return StatusApi(pulpcore_client)


@pytest.fixture(scope="session")
def users_api_client(pulpcore_client):
    return UsersApi(pulpcore_client)


@pytest.fixture(scope="session")
def users_roles_api_client(pulpcore_client):
    return UsersRolesApi(pulpcore_client)


@pytest.fixture(scope="session")
def signing_service_api_client(pulpcore_client):
    return SigningServicesApi(pulpcore_client)


@pytest.fixture
def gen_user(bindings_cfg, users_api_client, users_roles_api_client, gen_object_with_cleanup):
    class user_context:
        def __init__(self, username=None, model_roles=None, object_roles=None):
            self.username = username or str(uuid.uuid4())
            self.password = str(uuid.uuid4())
            self.user = gen_object_with_cleanup(
                users_api_client, {"username": self.username, "password": self.password}
            )
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
            self.saved_username, self.saved_password = (
                bindings_cfg.username,
                bindings_cfg.password,
            )
            bindings_cfg.username, bindings_cfg.password = self.username, self.password
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = (
                self.saved_username,
                self.saved_password,
            )

    return user_context


@pytest.fixture(scope="session")
def anonymous_user(bindings_cfg):
    class AnonymousUser:
        def __enter__(self):
            self.saved_username, self.saved_password = (
                bindings_cfg.username,
                bindings_cfg.password,
            )
            bindings_cfg.username, bindings_cfg.password = None, None
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = (
                self.saved_username,
                self.saved_password,
            )

    return AnonymousUser()


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
