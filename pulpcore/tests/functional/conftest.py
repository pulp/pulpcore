import pytest

from pulp_smash.pulp3.bindings import delete_orphans

from pulpcore.client.pulpcore import (
    ApiClient,
    TaskSchedulesApi,
)

from .conftest_pulp_file import *  # noqa


@pytest.fixture(scope="session")
def pulpcore_client(bindings_cfg):
    return ApiClient(bindings_cfg)


@pytest.fixture(scope="session")
def task_schedules_api_client(pulpcore_client):
    return TaskSchedulesApi(pulpcore_client)


@pytest.fixture
def delete_orphans_pre(request):
    if request.node.get_closest_marker("parallel") is not None:
        raise pytest.UsageError("This test is not suitable to be marked parallel.")
    delete_orphans()
    yield
