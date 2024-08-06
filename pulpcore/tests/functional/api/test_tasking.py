"""Tests related to the tasking system."""

import json
import pytest
import subprocess
import time
from aiohttp import BasicAuth
from urllib.parse import urljoin
from uuid import uuid4

from pulpcore.client.pulpcore import ApiException

from pulpcore.tests.functional.utils import download_file


@pytest.fixture(scope="session")
def dispatch_task(pulpcore_bindings):
    def _dispatch_task(*args, **kwargs):
        cid = pulpcore_bindings.client.default_headers.get("Correlation-ID") or str(uuid4())
        username = pulpcore_bindings.client.configuration.username
        commands = (
            "from django_guid import set_guid; "
            "from pulpcore.tasking.tasks import dispatch; "
            "from pulpcore.app.util import get_url, set_current_user; "
            "from django.contrib.auth import get_user_model; "
            "User = get_user_model(); "
            f"user = User.objects.filter(username='{username}').first(); "
            "set_current_user(user); "
            f"set_guid({cid!r}); "
            f"task = dispatch(*{args!r}, **{kwargs!r}); "
            "print(get_url(task))"
        )

        process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)

        assert process.returncode == 0
        task_href = process.stdout.decode().strip()
        return task_href

    return _dispatch_task


@pytest.fixture(scope="module")
def task(dispatch_task, monitor_task):
    """Fixture containing a Task."""
    task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    return monitor_task(task_href)


@pytest.mark.parallel
def test_multi_resource_locking(dispatch_task, monitor_task):
    task_href1 = dispatch_task(
        "pulpcore.app.tasks.test.sleep",
        args=(1,),
        exclusive_resources=["AAAA"],
        shared_resources=["BBBB"],
    )
    task_href2 = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(1,), shared_resources=["AAAA"]
    )
    task_href3 = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(1,), shared_resources=["AAAA"]
    )
    task_href4 = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(1,), exclusive_resources=["AAAA"]
    )
    task_href5 = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(1,), exclusive_resources=["BBBB"]
    )

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
def test_delete_cancel_waiting_task(dispatch_task, pulpcore_bindings):
    # Queue one task after a long running one
    resource = str(uuid4())
    blocking_task_href = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(600,), exclusive_resources=[resource]
    )
    task_href = dispatch_task(
        "pulpcore.app.tasks.test.sleep", args=(0,), exclusive_resources=[resource]
    )

    task = pulpcore_bindings.TasksApi.read(task_href)
    assert task.state == "waiting"

    # Try to delete first
    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.delete(task_href)
    assert ctx.value.status == 409

    # Now cancel the task
    task = pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})
    # cancel the blocking task
    pulpcore_bindings.TasksApi.tasks_cancel(blocking_task_href, {"state": "canceled"})

    if task.state == "canceling":
        assert task.started_at is None
        assert task.finished_at is None

        for i in range(10):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = pulpcore_bindings.TasksApi.read(task_href)

    assert task.state == "canceled"
    assert task.started_at is None
    assert task.finished_at is not None


@pytest.mark.parallel
def test_delete_cancel_running_task(dispatch_task, pulpcore_bindings):
    task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(600,))

    for i in range(10):
        task = pulpcore_bindings.TasksApi.read(task_href)
        if task.state == "running":
            break
        time.sleep(1)

    assert task.state == "running"

    # Try to delete first
    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.delete(task_href)
    assert ctx.value.status == 409

    # Now cancel the task
    task = pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})

    if task.state == "canceling":
        assert task.started_at is not None
        assert task.finished_at is None

        for i in range(10):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = pulpcore_bindings.TasksApi.read(task_href)

    assert task.state == "canceled"
    assert task.started_at is not None
    assert task.finished_at is not None


@pytest.mark.parallel
def test_cancel_delete_finished_task(pulpcore_bindings, dispatch_task, monitor_task):
    task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    monitor_task(task_href)

    # Try to cancel first
    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})
    assert ctx.value.status == 409

    # Now delete the task
    pulpcore_bindings.TasksApi.delete(task_href)


@pytest.mark.parallel
def test_cancel_nonexistent_task(pulp_api_v3_path, pulpcore_bindings):
    task_href = f"{pulp_api_v3_path}tasks/{uuid4()}/"
    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})
    assert ctx.value.status == 404


@pytest.mark.parallel
def test_retrieve_task_with_limited_fields(task, bindings_cfg):
    """Verify for specific fields retrieve in the payload."""
    expected_fields = set(("pulp_href", "state", "worker"))

    auth = BasicAuth(login=bindings_cfg.username, password=bindings_cfg.password)
    full_href = urljoin(bindings_cfg.host, task.pulp_href)

    response = download_file(f"{full_href}?fields={','.join(expected_fields)}", auth=auth)
    parsed_response = json.loads(response.body)

    returned_fields = set(parsed_response.keys())

    assert expected_fields == returned_fields


@pytest.mark.parallel
def test_retrieve_task_without_specific_fields(task, bindings_cfg):
    """Verify if some fields are excluded from the response."""
    unexpected_fields = set(("state", "worker"))

    auth = BasicAuth(login=bindings_cfg.username, password=bindings_cfg.password)
    full_href = urljoin(bindings_cfg.host, task.pulp_href)

    response = download_file(f"{full_href}?exclude_fields={','.join(unexpected_fields)}", auth=auth)
    parsed_response = json.loads(response.body)

    returned_fields = set(parsed_response.keys())

    assert unexpected_fields.isdisjoint(returned_fields)


@pytest.mark.parallel
def test_retrieve_task_with_minimal_fields(task, bindings_cfg):
    """Verify if some fields doesn't show when retrieving the minimal payload."""
    unexpected_fields = set(("progress_reports", "parent_task", "error"))

    auth = BasicAuth(login=bindings_cfg.username, password=bindings_cfg.password)
    full_href = urljoin(bindings_cfg.host, task.pulp_href)

    response = download_file(f"{full_href}?minimal=true", auth=auth)
    parsed_response = json.loads(response.body)

    returned_fields = set(parsed_response.keys())

    assert unexpected_fields.isdisjoint(returned_fields)


@pytest.mark.parallel
def test_retrieve_task_using_invalid_worker(pulpcore_bindings):
    """Expects to raise an exception when using invalid worker value as filter."""

    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.list(worker=str(uuid4()))

    assert ctx.value.status == 400


@pytest.mark.parallel
def test_retrieve_task_using_valid_worker(task, pulpcore_bindings):
    """Expects to retrieve a task using a valid worker URI as filter."""

    response = pulpcore_bindings.TasksApi.list(worker=task.worker)

    assert response.results and response.count


@pytest.mark.parallel
def test_retrieve_task_using_invalid_date(pulpcore_bindings):
    """Expects to raise an exception when using invalid dates as filters"""
    with pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.list(finished_at=str(uuid4()), started_at=str(uuid4()))

    assert ctx.value.status == 400


@pytest.mark.parallel
def test_retrieve_task_using_valid_date(task, pulpcore_bindings):
    """Expects to retrieve a task using a valid date."""

    response = pulpcore_bindings.TasksApi.list(started_at=task.started_at)

    assert response.results and response.count


@pytest.mark.parallel
def test_search_task_by_name(task, pulpcore_bindings):
    task_name = task.name
    search_results = pulpcore_bindings.TasksApi.list(name=task.name).results

    assert search_results
    assert all([task.name == task_name for task in search_results])


@pytest.mark.parallel
def test_search_task_using_an_invalid_name(pulpcore_bindings):
    """Expect to return an empty results array when searching using an invalid
    task name.
    """

    search_results = pulpcore_bindings.TasksApi.list(name=str(uuid4()))

    assert not search_results.results and not search_results.count


@pytest.mark.parallel
def test_filter_tasks_using_worker__in_filter(pulpcore_bindings, dispatch_task, monitor_task):
    task1_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    task2_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))

    task1 = monitor_task(task1_href)
    task2 = monitor_task(task2_href)

    search_results = pulpcore_bindings.TasksApi.list(worker__in=(task1.worker, task2.worker))

    tasks_hrefs = [task.pulp_href for task in search_results.results]

    assert task1_href in tasks_hrefs
    assert task2_href in tasks_hrefs


def test_cancel_gooey_task(pulpcore_bindings, dispatch_task, monitor_task):
    task_href = dispatch_task("pulpcore.app.tasks.test.gooey_task", args=(60,))
    for i in range(10):
        task = pulpcore_bindings.TasksApi.read(task_href)
        if task.state == "running":
            break
        time.sleep(1)

    task = pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})

    if task.state == "canceling":
        for i in range(30):
            if task.state != "canceling":
                break
            time.sleep(1)
            task = pulpcore_bindings.TasksApi.read(task_href)

    assert task.state == "canceled"


@pytest.mark.parallel
def test_task_created_by(dispatch_task, monitor_task, gen_user, anonymous_user):
    # Test admin dispatch, user_id == 1 / admin is always first user
    task = monitor_task(dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,)))
    assert task.created_by.endswith("/1/")

    # Test w/ new user, user_id != 1
    user = gen_user()
    with user:
        task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    user_task = monitor_task(task_href)
    assert task.created_by != user_task.created_by
    assert user_task.created_by == user.user.pulp_href

    # Test w/ anon (Pulp itself, i.e. analytics)
    with anonymous_user:
        task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    anon_task = monitor_task(task_href)
    assert anon_task.created_by is None


@pytest.mark.parallel
def test_task_version_prevent_pickup(dispatch_task, pulpcore_bindings):
    task1 = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,), versions={"core": "4.0.0"})
    task2 = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,), versions={"catdog": "0.0.0"})

    time.sleep(5)
    for task_href in [task1, task2]:
        task = pulpcore_bindings.TasksApi.read(task_href)
        assert task.state == "waiting"
        pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})


@pytest.mark.parallel
def test_correct_task_ownership(
    dispatch_task, pulpcore_bindings, gen_user, file_repository_factory
):
    """Test that tasks get the correct ownership when dispatched."""
    alice = gen_user(model_roles=["core.task_viewer"])
    bob = gen_user(model_roles=["file.filerepository_creator"])

    with alice:
        atask_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    aroles = pulpcore_bindings.UsersRolesApi.list(alice.user.pulp_href)
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
        repo = file_repository_factory()
    aroles = pulpcore_bindings.UsersRolesApi.list(alice.user.pulp_href)
    assert aroles.count == 3
    broles = pulpcore_bindings.UsersRolesApi.list(bob.user.pulp_href)
    assert broles.count == 4
    roles = {r.role: r.content_object for r in broles.results}
    correct_roles = {
        "core.task_owner": btask_href,
        "core.task_user_dispatcher": btask_href,
        "file.filerepository_owner": repo.pulp_href,
        "file.filerepository_creator": None,
    }
    assert roles == correct_roles
