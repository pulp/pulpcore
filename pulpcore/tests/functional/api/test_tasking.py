"""Tests related to the tasking system."""

import json
import pytest
import time

from aiohttp import BasicAuth
from datetime import datetime
from urllib.parse import urljoin
from uuid import uuid4

from pulpcore.client.pulpcore import ApiException
from contextlib import contextmanager

from pulpcore.tests.functional.utils import download_file, PulpTaskError
from pulpcore.constants import IMMEDIATE_TIMEOUT


@pytest.fixture(scope="module")
def task(dispatch_task, monitor_task):
    """Fixture containing a finished Task."""
    task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    return monitor_task(task_href)


@pytest.mark.parallel
def test_retrieving_task_profile_artifacts(gen_user, pulpcore_bindings, task):
    with gen_user(model_roles=["core.task_viewer"]), pytest.raises(ApiException) as ctx:
        pulpcore_bindings.TasksApi.profile_artifacts(task.pulp_href)
    assert ctx.value.status == 403

    with gen_user(model_roles=["core.task_owner"]):
        assert pulpcore_bindings.TasksApi.profile_artifacts(task.pulp_href).urls is not None


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


@pytest.mark.parallel
def test_filter_tasks_using_pulp_created_filter(pulpcore_bindings, dispatch_task):

    task1_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))

    time.sleep(2)
    start_time = datetime.now()
    task2_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))
    task3_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,))

    search_results_gte = pulpcore_bindings.TasksApi.list(pulp_created__gte=start_time)

    tasks_hrefs_gte = [task.pulp_href for task in search_results_gte.results]

    assert task1_href not in tasks_hrefs_gte
    assert task2_href in tasks_hrefs_gte
    assert task3_href in tasks_hrefs_gte

    search_results_lte = pulpcore_bindings.TasksApi.list(pulp_created__lte=start_time)

    tasks_hrefs_lte = [task.pulp_href for task in search_results_lte.results]

    assert task1_href in tasks_hrefs_lte
    assert task2_href not in tasks_hrefs_lte
    assert task3_href not in tasks_hrefs_lte


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


@pytest.fixture
def task_group(dispatch_task_group, monitor_task_group):
    """Fixture containing a finished Task Group."""
    kwargs = {"inbetween": 0, "intervals": [0]}
    tgroup_href = dispatch_task_group("pulpcore.app.tasks.test.dummy_group_task", kwargs=kwargs)
    return monitor_task_group(tgroup_href)


@pytest.mark.parallel
def test_scope_task_groups(pulpcore_bindings, task_group, gen_user):
    """Test that task groups can be queryset scoped by permission on Tasks."""
    for task in task_group.tasks:
        if task.name == "pulpcore.app.tasks.test.dummy_group_task":
            break

    response = pulpcore_bindings.TaskGroupsApi.list()
    assert response.count > 0

    with gen_user():
        response = pulpcore_bindings.TaskGroupsApi.list()
        assert response.count == 0

    with gen_user(model_roles=["core.task_viewer"]):
        response = pulpcore_bindings.TaskGroupsApi.list()
        assert response.count > 0

    with gen_user(object_roles=[("core.task_owner", task.pulp_href)]):
        response = pulpcore_bindings.TaskGroupsApi.list()
        assert response.count == 1


@pytest.mark.parallel
def test_cancel_task_group(pulpcore_bindings, dispatch_task_group, gen_user):
    """Test that task groups can be canceled."""
    kwargs = {"inbetween": 1, "intervals": [10, 10, 10, 10, 10]}
    tgroup_href = dispatch_task_group("pulpcore.app.tasks.test.dummy_group_task", kwargs=kwargs)

    tgroup = pulpcore_bindings.TaskGroupsApi.task_groups_cancel(tgroup_href, {"state": "canceled"})
    for task in tgroup.tasks:
        assert task.state in ["canceled", "canceling"]

    with gen_user(model_roles=["core.task_viewer"]), pytest.raises(
        pulpcore_bindings.ApiException
    ) as e:
        pulpcore_bindings.TaskGroupsApi.task_groups_cancel(tgroup_href, {"state": "canceled"})
        assert "You do not have permission" in e.value.message

    if len(tgroup.tasks) > 1:
        one_role = [("core.task_owner", task.pulp_href)]
        with gen_user(object_roles=one_role), pytest.raises(pulpcore_bindings.ApiException) as e:
            pulpcore_bindings.TaskGroupsApi.task_groups_cancel(tgroup_href, {"state": "canceled"})
            assert "You do not have permission" in e.value.message

    with gen_user(model_roles=["core.task_owner"]):
        pulpcore_bindings.TaskGroupsApi.task_groups_cancel(tgroup_href, {"state": "canceled"})


LT_TIMEOUT = IMMEDIATE_TIMEOUT / 2
GT_TIMEOUT = IMMEDIATE_TIMEOUT * 2


class TestImmediateTaskWithNoResource:

    @pytest.mark.parallel
    def test_succeeds_on_api_worker(self, pulpcore_bindings, dispatch_task):
        """
        GIVEN a task with no resource requirements
        AND the task IS an async function
        WHEN dispatching a task as immediate
        THEN the task completes with no associated worker
        """
        task_href = dispatch_task(
            "pulpcore.app.tasks.test.asleep", args=(LT_TIMEOUT,), immediate=True
        )
        task = pulpcore_bindings.TasksApi.read(task_href)
        assert task.state == "completed"
        assert task.worker is None

    @pytest.mark.parallel
    def test_executes_on_api_worker_when_no_async(self, pulpcore_bindings, dispatch_task, capsys):
        """
        GIVEN a task with no resource requirements
        AND the task IS NOT an async function
        WHEN dispatching a task as immediate
        THEN the task completes with no associated worker
        """
        # TODO: on 3.85 this should throw an error
        task_href = dispatch_task(
            "pulpcore.app.tasks.test.sleep", args=(LT_TIMEOUT,), immediate=True
        )
        stderr_content = capsys.readouterr().err
        task = pulpcore_bindings.TasksApi.read(task_href)
        assert task.state == "completed"
        assert task.worker is None
        assert "Support for non-coroutine immediate tasks will be dropped" in stderr_content

    @pytest.mark.parallel
    def test_timeouts_on_api_worker(self, pulpcore_bindings, dispatch_task):
        """
        GIVEN a task with no resource requirements
        AND the task is an async function
        WHEN dispatching a task as immediate
        AND it takes longer than timeout
        THEN the task fails with a timeout error message
        """
        task_href = dispatch_task(
            "pulpcore.app.tasks.test.asleep", args=(GT_TIMEOUT,), immediate=True
        )
        task = pulpcore_bindings.TasksApi.read(task_href)
        assert task.worker is None
        assert "task timed out after" in task.error["description"]


@pytest.fixture
def resource_blocker(pulpcore_bindings, dispatch_task):

    @contextmanager
    def _resource_blocker(exclusive_resources: list[str], duration=20):
        task_href = dispatch_task(
            "pulpcore.app.tasks.test.sleep",
            args=(duration,),
            exclusive_resources=exclusive_resources,
        )
        yield
        # Trying to cancel a finished task will return a 409 code.
        # We can ignore if that's the case, because all we want here is to cut time down.
        # Otherwise it might be a real error.
        try:
            pulpcore_bindings.TasksApi.tasks_cancel(task_href, {"state": "canceled"})
        except ApiException as e:
            if e.status != 409:
                raise

    return _resource_blocker


class TestImmediateTaskWithBlockedResource:

    @pytest.mark.parallel
    def test_executes_in_task_worker(
        self, resource_blocker, dispatch_task, monitor_task, pulpcore_bindings
    ):
        """
        GIVEN an async task requiring busy resources
        WHEN dispatching a task as immediate
        THEN the task completes with a worker
        """
        COMMON_RESOURCE = str(uuid4())
        with resource_blocker(exclusive_resources=[COMMON_RESOURCE]):
            task_href = dispatch_task(
                "pulpcore.app.tasks.test.asleep",
                args=(LT_TIMEOUT,),
                immediate=True,
                exclusive_resources=[COMMON_RESOURCE],
            )
        task = monitor_task(task_href)
        assert task.state == "completed"
        assert task.worker is not None

    @pytest.mark.parallel
    def test_throws_when_non_deferrable(
        self, resource_blocker, pulpcore_bindings, dispatch_task, monitor_task
    ):
        """
        GIVEN an async task requiring busy resources
        WHEN dispatching as immediate and not deferrable
        THEN an error is raised
        """
        COMMON_RESOURCE = str(uuid4())
        with resource_blocker(exclusive_resources=[COMMON_RESOURCE]):
            task_href = dispatch_task(
                "pulpcore.app.tasks.test.asleep",
                args=(0,),
                immediate=True,
                deferred=False,
                exclusive_resources=[COMMON_RESOURCE],
            )
            task = pulpcore_bindings.TasksApi.read(task_href)
            assert task.state == "canceled"
            assert task.worker is None
            assert "Resources temporarily unavailable." in task.error["reason"]

    @pytest.mark.parallel
    def test_times_out_on_task_worker(
        self, resource_blocker, pulpcore_bindings, dispatch_task, monitor_task
    ):
        """
        GIVEN an async task requiring busy resources
        WHEN dispatching a task as immediate
        AND it takes longer than timeout
        THEN an error is raised
        """
        COMMON_RESOURCE = str(uuid4())
        with pytest.raises(PulpTaskError) as ctx:
            with resource_blocker(exclusive_resources=[COMMON_RESOURCE]):
                task_href = dispatch_task(
                    "pulpcore.app.tasks.test.asleep",
                    args=(GT_TIMEOUT,),
                    immediate=True,
                    exclusive_resources=[COMMON_RESOURCE],
                )
            monitor_task(task_href)
        assert "task timed out after" in ctx.value.task.error["description"]
