import asyncio
import os
import shutil
import uuid
from time import sleep

import aiohttp
import pytest

from pulpcore.client.pulpcore import (
    ApiClient,
    TasksApi,
    UsersApi,
    UsersRolesApi,
)

from pulpcore.tests.functional.utils import (
    SLEEP_TIME,
    PulpTaskError,
    PulpTaskGroupError,
)


@pytest.fixture(scope="session")
def pulpcore_client(bindings_cfg):
    return ApiClient(bindings_cfg)


@pytest.fixture
def users_api_client(pulpcore_client):
    return UsersApi(pulpcore_client)


@pytest.fixture
def users_roles_api_client(pulpcore_client):
    return UsersRolesApi(pulpcore_client)


@pytest.fixture(scope="session")
def tasks_api_client(pulpcore_client):
    return TasksApi(pulpcore_client)


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
def random_artifact_factory(artifacts_api_client, tmp_path, gen_object_with_cleanup):
    def _random_artifact_factory():
        temp_file = tmp_path / str(uuid.uuid4())
        temp_file.write_bytes(uuid.uuid4().bytes)
        return artifacts_api_client.create(temp_file)

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
def monitor_task(tasks_api_client):
    def _monitor_task(task_href):
        task = tasks_api_client.read(task_href)
        while task.state not in ["completed", "failed", "canceled"]:
            sleep(SLEEP_TIME)
            task = tasks_api_client.read(task_href)

        if task.state != "completed":
            raise PulpTaskError(task=task)

        return task

    return _monitor_task


@pytest.fixture(scope="session")
def monitor_task_group(task_groups_api_client):
    def _monitor_task_group(task_group_href):
        task_group = task_groups_api_client.read(task_group_href)

        while not task_group.all_tasks_dispatched or (task_group.waiting + task_group.running) > 0:
            sleep(SLEEP_TIME)
            task_group = task_groups_api_client.read(task_group_href)

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
def pulp_api_v3_path(pulp_settings):
    v3_api_root = pulp_settings.V3_API_ROOT
    if v3_api_root is None:
        raise RuntimeError(
            "This fixture requires the server to have the `V3_API_ROOT` setting set."
        )
    return v3_api_root


@pytest.fixture(scope="session")
def pulp_api_v3_url(bindings_cfg, pulp_api_v3_path):
    return f"{bindings_cfg.host}{pulp_api_v3_path}"


@pytest.fixture
def get_redis_status(status_api_client):
    """Return a boolean value which tells whether the connection to redis was established or not."""
    status_response = status_api_client.status_read()
    return status_response.redis_connection.connected


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
def download_content_unit(bindings_cfg):
    def _download_content_unit(base_path, content_path):
        async def _get_response(url):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.read()

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
