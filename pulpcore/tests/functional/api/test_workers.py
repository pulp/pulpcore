"""Tests related to the workers."""
import pytest
import subprocess
from datetime import datetime, timedelta
from random import choice
from time import sleep


_DYNAMIC_WORKER_ATTRS = ("last_heartbeat", "current_task")
"""Worker attributes that are dynamically set by Pulp, not set by a user."""


@pytest.mark.parallel
def test_worker_actions(workers_api_client):
    # Read all workers.
    workers = workers_api_client.list().results
    for worker in workers:
        for key, val in worker.to_dict().items():
            if key in _DYNAMIC_WORKER_ATTRS:
                continue
            assert val is not None

    # Pick a random worker to be used for the next assertions.
    chosen_worker = choice(workers)

    # Read a worker by its pulp_href.
    read_worker = workers_api_client.read(chosen_worker.pulp_href)
    for key, val in chosen_worker.to_dict().items():
        if key in _DYNAMIC_WORKER_ATTRS:
            continue
        assert getattr(read_worker, key) == val

    # Read a worker by its name.
    response = workers_api_client.list(name=chosen_worker.name)
    assert response.count == 1
    found_worker = response.results[0]
    for key, val in chosen_worker.to_dict().items():
        if key in _DYNAMIC_WORKER_ATTRS:
            continue
        assert getattr(found_worker, key) == val

    # Read a worker using a set of query parameters.
    response = workers_api_client.list(
        **{
            "last_heartbeat__gte": chosen_worker.last_heartbeat,
            "name": chosen_worker.name,
        },
    )
    assert response.count == 1
    found_worker = response.results[0]
    for key, val in chosen_worker.to_dict().items():
        if key in _DYNAMIC_WORKER_ATTRS:
            continue
        assert getattr(found_worker, key) == val

    # Read a worker with a query that does not match any worker.
    response = workers_api_client.list(
        **{
            "last_heartbeat__gte": str(datetime.now() + timedelta(days=1)),
            "name": chosen_worker.name,
        },
    )
    assert response.count == 0

    # Use an HTTP method different than GET
    with pytest.raises(AttributeError):
        workers_api_client.delete(chosen_worker.pulp_href)


@pytest.fixture
def task_schedule():
    name = "test_schedule"
    task_name = "pulpcore.app.tasks.test.dummy_task"
    schedule_commands = (
        "from django.utils.timezone import now;"
        "from datetime import timedelta;"
        "from pulpcore.app.models import TaskSchedule;"
        "dispatch_interval = timedelta(seconds=4);"
        "next_dispatch = now() + dispatch_interval;"
        "TaskSchedule("
        f"    name='{name}', task_name='{task_name}', "
        "    dispatch_interval=dispatch_interval, next_dispatch=next_dispatch"
        ").save();"
    )
    process = subprocess.run(["pulpcore-manager", "shell", "-c", schedule_commands])
    assert process.returncode == 0

    yield {"name": name, "task_name": task_name}

    unschedule_commands = (
        "from pulpcore.app.models import TaskSchedule;"
        f"TaskSchedule.objects.get(name='{name}').delete();"
    )
    process = subprocess.run(["pulpcore-manager", "shell", "-c", unschedule_commands])
    assert process.returncode == 0


@pytest.mark.parallel
def test_task_schedule(task_schedule, task_schedules_api_client):
    """Test that a worker will schedule a task roughly at a given time."""
    # Worker TTL is configured to 30s, therefore they will have a heartbeat each 10s (6 bpm). The
    # task is scheduled 4s in the future to give us time to invesitgate the state before and after.
    # 15s later we can be sure it was scheduled (as long as at least one worker is running).

    result = task_schedules_api_client.list(name=task_schedule["name"])
    assert result.count == 1
    ts = task_schedules_api_client.read(task_schedule_href=result.results[0].pulp_href)
    assert ts.name == task_schedule["name"]
    assert ts.task_name == task_schedule["task_name"]
    assert ts.last_task is None
    # At least a worker heartbeat is needed
    for i in range(15):
        sleep(1)
        ts = task_schedules_api_client.read(task_schedule_href=result.results[0].pulp_href)
        if ts.last_task is not None:
            break
    assert ts.last_task is not None
