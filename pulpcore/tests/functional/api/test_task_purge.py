"""Tests task-purge functionality."""

from datetime import datetime, timedelta, timezone

import pytest

from pulpcore.constants import TASK_FINAL_STATES

from pulpcore.tests.functional.utils import PulpTaskError

TOMORROW_STR = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


def _purge_report_total(task):
    for report in task.progress_reports:
        if report.code == "purge.tasks.total":
            return report.total
    pytest.fail("NO PURGE_TASKS_TOTAL?!?")


@pytest.fixture
def good_and_bad_task(
    pulpcore_bindings,
    dispatch_task,
    monitor_task,
):
    good_task = monitor_task(dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,)))
    assert good_task.state == "completed"

    bad_task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(-1,))
    with pytest.raises(PulpTaskError):
        monitor_task(bad_task_href)
    bad_task = pulpcore_bindings.TasksApi.read(bad_task_href)
    assert bad_task.state == "failed"

    return good_task, bad_task


def test_purge_before_deletes_all_tasks(pulpcore_bindings, good_and_bad_task, monitor_task):
    """Purge that should find no tasks to delete."""
    good_task, bad_task = good_and_bad_task
    response = pulpcore_bindings.TasksApi.purge({"finished_before": "1970-01-01T00:00"})
    task = monitor_task(response.task)
    pulpcore_bindings.TasksApi.read(good_task.pulp_href)
    pulpcore_bindings.TasksApi.read(bad_task.pulp_href)
    assert _purge_report_total(task) == 0


def test_purge_with_defaults_spares_recent_tasks(
    pulpcore_bindings, good_and_bad_task, monitor_task
):
    """Purge using defaults (finished_before=30-days-ago, state=completed)"""
    good_task, bad_task = good_and_bad_task

    response = pulpcore_bindings.TasksApi.purge({})
    monitor_task(response.task)

    # Recent tasks should still be there.
    pulpcore_bindings.TasksApi.read(good_task.pulp_href)
    pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_purge_with_future_time_and_all_final_states_deletes_all_tasks(
    pulpcore_bindings, good_and_bad_task, monitor_task
):
    """Purge all tasks in any 'final' state."""
    good_task, bad_task = good_and_bad_task

    response = pulpcore_bindings.TasksApi.purge(
        {"finished_before": TOMORROW_STR, "states": TASK_FINAL_STATES}
    )
    monitor_task(response.task)

    # Both tasks should be gone.
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(good_task.pulp_href)
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_purge_with_time_between_leaves_never_task(
    pulpcore_bindings, good_and_bad_task, monitor_task
):
    """Arrange to leave one task unscathed."""
    good_task, bad_task = good_and_bad_task

    response = pulpcore_bindings.TasksApi.purge({"finished_before": bad_task.finished_at})
    monitor_task(response.task)

    # Only the newer task should be left
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(good_task.pulp_href)
    pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_purge_only_failed_removes_good_task(pulpcore_bindings, good_and_bad_task, monitor_task):
    """Purge all failed tasks only."""
    good_task, bad_task = good_and_bad_task
    response = pulpcore_bindings.TasksApi.purge(
        {"finished_before": TOMORROW_STR, "states": ["failed"]}
    )
    monitor_task(response.task)

    # Only the good task should be left.
    pulpcore_bindings.TasksApi.read(good_task.pulp_href)
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_bad_date(pulpcore_bindings, good_and_bad_task):
    """What happens if you use a bad date format?"""
    with pytest.raises((pulpcore_bindings.ApiException, ValueError)):
        dta = pulpcore_bindings.Purge(finished_before="THISISNOTADATE")
        pulpcore_bindings.TasksApi.purge(dta)


def test_bad_state(pulpcore_bindings, good_and_bad_task):
    """What happens if you specify junk for a state?"""
    with pytest.raises((pulpcore_bindings.ApiException, ValueError)):
        dta = pulpcore_bindings.Purge(finished_before=TOMORROW_STR, states=["BAD STATE"])
        pulpcore_bindings.TasksApi.purge(dta)


def test_not_final_state(pulpcore_bindings, good_and_bad_task):
    """What happens if you use a valid state that isn't a 'final' one?"""
    with pytest.raises((pulpcore_bindings.ApiException, ValueError)):
        dta = pulpcore_bindings.Purge(finished_before=TOMORROW_STR, states=["running"])
        pulpcore_bindings.TasksApi.purge(dta)


def test_purge_with_different_users(
    pulpcore_bindings,
    file_bindings,
    file_remote_ssl_factory,
    file_repository_factory,
    basic_manifest_path,
    gen_user,
    monitor_task,
):
    # create admin related data
    admin_remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
    admin_sync_data = file_bindings.RepositorySyncURL(remote=admin_remote.pulp_href)
    admin_repo = file_repository_factory()

    # create random user related data
    user = gen_user(
        model_roles=[
            "file.filerepository_owner",
            "file.filerepository_creator",
            "file.fileremote_creator",
        ]
    )
    with user:
        user_remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="on_demand")
        user_sync_data = file_bindings.RepositorySyncURL(remote=user_remote.pulp_href)
        user_repo = file_repository_factory()

    # Sync as admin
    sync_response = file_bindings.RepositoriesFileApi.sync(admin_repo.pulp_href, admin_sync_data)
    monitor_task(sync_response.task)

    # Purge as user
    states = list(TASK_FINAL_STATES)
    data = pulpcore_bindings.Purge(finished_before=TOMORROW_STR, states=states)
    with user:
        response = pulpcore_bindings.TasksApi.purge(data)
        task = monitor_task(response.task)

    # Make sure sync-task (executed by admin) still exists
    pulpcore_bindings.TasksApi.read(task.pulp_href)

    # Sync as user
    with user:
        sync_response = file_bindings.RepositoriesFileApi.sync(user_repo.pulp_href, user_sync_data)
        sync_task = monitor_task(sync_response.task)

    # Purge as user
    states = list(TASK_FINAL_STATES)
    data = pulpcore_bindings.Purge(finished_before=TOMORROW_STR, states=states)
    with user:
        response = pulpcore_bindings.TasksApi.purge(data)
        monitor_task(response.task)

    # Make sure task DOES NOT exist
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(sync_task.pulp_href)

    # Sync as user
    with user:
        sync_response = file_bindings.RepositoriesFileApi.sync(user_repo.pulp_href, user_sync_data)
        monitor_task(sync_response.task)

    # Purge as ADMIN
    states = list(TASK_FINAL_STATES)
    data = pulpcore_bindings.Purge(finished_before=TOMORROW_STR, states=states)
    response = pulpcore_bindings.TasksApi.purge(data)
    monitor_task(response.task)

    # Make sure task DOES NOT exist
    with pytest.raises(pulpcore_bindings.ApiException):
        pulpcore_bindings.TasksApi.read(sync_task.pulp_href)
