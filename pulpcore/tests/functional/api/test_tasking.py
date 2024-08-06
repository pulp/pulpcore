"""Tests related to the tasking system."""

import pytest
import subprocess
import time
from uuid import uuid4

from pulp_smash.pulp3.bindings import monitor_task
from pulpcore.client.pulpcore import ApiException


@pytest.fixture
def dispatch_task(pulpcore_client):
    def _dispatch_task(*args, **kwargs):
        cid = pulpcore_client.default_headers.get("Correlation-ID") or str(uuid4())
        username = pulpcore_client.configuration.username
        commands = (
            "from django_guid import set_guid; "
            "from pulpcore.tasking.tasks import dispatch; "
            "from pulpcore.app.util import get_url; "
            "from django.contrib.auth import get_user_model; "
            "from django_currentuser.middleware import _set_current_user; "
            "User = get_user_model(); "
            f"user = User.objects.filter(username='{username}').first(); "
            "_set_current_user(user); "
            f"set_guid({cid!r}); "
            f"task = dispatch(*{args!r}, **{kwargs!r}); "
            "print(get_url(task))"
        )

        process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)

        assert process.returncode == 0
        task_href = process.stdout.decode().strip()
        return task_href

    return _dispatch_task


@pytest.fixture
def task(dispatch_task):
    """Fixture containing a Task."""
    task_href = dispatch_task("time.sleep", args=(0,))
    return monitor_task(task_href)


@pytest.mark.parallel
def test_multi_resource_locking(dispatch_task):
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
    # cancel the blocking task
    tasks_api_client.tasks_cancel(blocking_task_href, {"state": "canceled"})

    if task.state == "canceling":
        assert task.started_at is None
        assert task.finished_at is None

        for i in range(10):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = tasks_api_client.read(task_href)

    assert task.state == "canceled"
    assert task.started_at is None
    assert task.finished_at is not None


@pytest.mark.skip(reason="This is too unpredictable in this old version.")
@pytest.mark.parallel
def test_delete_cancel_running_task(dispatch_task, tasks_api_client):
    task_href = dispatch_task("time.sleep", args=(600,))

    for i in range(10):
        task = tasks_api_client.read(task_href)
        if task.state == "running":
            break
        time.sleep(1)

    assert task.state == "running"

    # Try to delete first
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.delete(task_href)
    assert ctx.value.status == 409

    # Now cancel the task
    task = tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})

    if task.state == "canceling":
        assert task.started_at is not None
        assert task.finished_at is None

        for i in range(10):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = tasks_api_client.read(task_href)

    assert task.state == "canceled"
    assert task.started_at is not None
    assert task.finished_at is not None


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


@pytest.mark.parallel
def test_retrieve_task_using_invalid_worker(tasks_api_client):
    """Expects to raise an exception when using invalid worker value as filter."""

    with pytest.raises(ApiException) as ctx:
        tasks_api_client.list(worker=str(uuid4()))

    assert ctx.value.status == 400


@pytest.mark.parallel
def test_retrieve_task_using_valid_worker(task, tasks_api_client):
    """Expects to retrieve a task using a valid worker URI as filter."""

    response = tasks_api_client.list(worker=task.worker)

    assert response.results and response.count


@pytest.mark.parallel
def test_retrieve_task_using_invalid_date(tasks_api_client):
    """Expects to raise an exception when using invalid dates as filters"""
    with pytest.raises(ApiException) as ctx:
        tasks_api_client.list(finished_at=str(uuid4()), started_at=str(uuid4()))

    assert ctx.value.status == 400


@pytest.mark.parallel
def test_retrieve_task_using_valid_date(task, tasks_api_client):
    """Expects to retrieve a task using a valid date."""

    response = tasks_api_client.list(started_at=task.started_at)

    assert response.results and response.count


@pytest.mark.parallel
def test_search_task_by_name(task, tasks_api_client):
    task_name = task.name
    search_results = tasks_api_client.list(name=task.name).results

    assert search_results
    assert all([task.name == task_name for task in search_results])


@pytest.mark.parallel
def test_search_task_using_an_invalid_name(tasks_api_client):
    """Expect to return an empty results array when searching using an invalid
    task name.
    """

    search_results = tasks_api_client.list(name=str(uuid4()))

    assert not search_results.results and not search_results.count


def test_cancel_gooey_task(tasks_api_client, dispatch_task):
    task_href = dispatch_task("pulpcore.app.tasks.test.gooey_task", (60,))
    for i in range(10):
        task = tasks_api_client.read(task_href)
        if task.state == "running":
            break
        time.sleep(1)

    task = tasks_api_client.tasks_cancel(task_href, {"state": "canceled"})

    if task.state == "canceling":
        for i in range(30):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = tasks_api_client.read(task_href)

    assert task.state == "canceled"


@pytest.mark.parallel
def test_correct_task_ownership(dispatch_task, users_roles_api_client, gen_user):
    """Test that tasks get the correct ownership when dispatched."""
    alice = gen_user(model_roles=["core.task_viewer"])
    bob = gen_user(model_roles=["file.filerepository_creator"])

    with alice:
        atask_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    aroles = users_roles_api_client.list(alice.user.pulp_href)
    assert aroles.count == 3
    roles = {r.role: r.content_object for r in aroles.results}
    correct_roles = {
        "core.task_owner": atask_href,
        "core.task_user_dispatcher": atask_href,
        "core.task_viewer": None,
    }
    assert roles == correct_roles

    with bob:
        btask_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    aroles = users_roles_api_client.list(alice.user.pulp_href)
    assert aroles.count == 3
    broles = users_roles_api_client.list(bob.user.pulp_href)
    assert broles.count == 3
    roles = {r.role: r.content_object for r in broles.results}
    correct_roles = {
        "core.task_owner": btask_href,
        "core.task_user_dispatcher": btask_href,
        "file.filerepository_creator": None,
    }
    assert roles == correct_roles
