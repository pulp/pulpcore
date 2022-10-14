"""Tests related to the tasking system."""
import pytest
import subprocess
import time
from uuid import uuid4

from pulp_smash.pulp3.bindings import monitor_task
from pulpcore.client.pulpcore import ApiException


@pytest.fixture
def dispatch_task(cid):
    def _dispatch_task(*args, **kwargs):
        commands = (
            "import django; "
            "django.setup(); "
            "from django_guid import set_guid; "
            "from pulpcore.tasking.tasks import dispatch; "
            "from pulpcore.app.util import get_url; "
            f"set_guid({cid!r}); "
            f"task = dispatch(*{args!r}, **{kwargs!r}); "
            "print(get_url(task))"
        )

        process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)

        assert process.returncode == 0
        task_href = process.stdout.decode().strip()
        return task_href

    return _dispatch_task


@pytest.mark.parallel
def test_multi_resource_locking(tasks_api_client, dispatch_task):
    task_href1 = dispatch_task(
        "time.sleep", args=(1,), exclusive_resources=["AAAA"], shared_resources=["BBBB"]
    )
    task_href2 = dispatch_task("time.sleep", args=(1,), shared_resources=["AAAA"])
    task_href3 = dispatch_task("time.sleep", args=(1,), shared_resources=["AAAA"])
    task_href4 = dispatch_task("time.sleep", args=(1,), exclusive_resources=["AAAA"])
    task_href5 = dispatch_task("time.sleep", args=(1,), exclusive_resources=["BBBB"])

    task1 = monitor_task(task_href1)
    task2 = monitor_task(task_href2)
    task3 = monitor_task(task_href3)
    task4 = monitor_task(task_href4)
    task5 = monitor_task(task_href5)

    assert task1.finished_at < task2.started_at
    assert task1.finished_at < task3.started_at
    assert task2.finished_at < task4.started_at
    assert task3.finished_at < task4.started_at
    assert task1.finished_at < task5.started_at


@pytest.mark.parallel
def test_delete_cancel_waiting_task(dispatch_task, tasks_api_client):
    # Queue one task after a long running one
    resource = str(uuid4())
    blocking_task_href = dispatch_task("time.sleep", args=(600,), exclusive_resources=[resource])
    task_href = dispatch_task("time.sleep", args=(0,), exclusive_resources=[resource])

    task = tasks_api_client.read(task_href)
    assert task.state == "waiting"

    # Try to delete first
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.delete(task_href)
    assert ctx.value.status == 409

    # Now cancel the task
    task = tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})

    assert task.started_at is None
    assert task.finished_at is None
    assert task.state == "canceling"

    # cancel the blocking task
    task = tasks_api_client.tasks_cancel(blocking_task_href, {"state": "canceled"})

    for i in range(10):
        task = tasks_api_client.read(task_href)
        if task.state != "canceling":
            break
        time.sleep(1)

    assert task.state == "canceled"


@pytest.mark.parallel
def test_delete_cancel_running_task(dispatch_task, tasks_api_client):
    task_href = dispatch_task("time.sleep", args=(600,))

    for i in range(10):
        task = tasks_api_client.read(task_href)
        if task.state != "running":
            break
        time.sleep(1)

    assert task.state == "running"

    # Try to delete first
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.delete(task_href)
    assert ctx.value.status == 409

    # Now cancel the task
    task = tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})

    assert task.started_at is not None
    assert task.finished_at is None
    assert task.state == "canceling"

    for i in range(10):
        task = tasks_api_client.read(task_href)
        if task.state != "canceling":
            break
        time.sleep(1)

    assert task.state == "canceled"


@pytest.mark.parallel
def test_cancel_delete_finished_task(tasks_api_client, dispatch_task):
    task_href = dispatch_task("time.sleep", args=(0,))
    monitor_task(task_href)

    # Try to cancel first
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})
    assert ctx.value.status == 409

    # Now delete the task
    tasks_api_client.delete(task_href)


@pytest.mark.parallel
def test_cancel_nonexistent_task(pulp_api_v3_path, tasks_api_client):
    task_href = f"{pulp_api_v3_path}tasks/{uuid4()}/"
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})
    assert ctx.value.status == 404
