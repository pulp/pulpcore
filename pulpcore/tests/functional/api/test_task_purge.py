"""
Tests task-purge functionality.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pulpcore.client.pulpcore import ApiException, Purge
from pulpcore.client.pulp_file import RepositorySyncURL

from pulpcore.constants import TASK_STATES, TASK_FINAL_STATES

from pulpcore.tests.functional.utils import PulpTaskError

TOMORROW_STR = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


def _task_summary(pulpcore_bindings):
    """
    Summary of number of tasks in all known task-states.
    :return: tuple of (total-tasks, number of final tasks, summary)
    """
    summary = {}
    total = 0
    final_total = 0
    for state in TASK_STATES.__dict__.values():
        response = pulpcore_bindings.TasksApi.list(state=state)
        summary[state] = response.count
        total += summary[state]
        final_total += summary[state] if state in TASK_FINAL_STATES else 0
    return total, final_total, summary


def _purge_report_total(task):
    for report in task.progress_reports:
        if report.code == "purge.tasks.total":
            return report.total
    pytest.fail("NO PURGE_TASKS_TOTAL?!?")


def _check_delete_report(task, expected, fuzzy=False):
    # Make sure we reported the deletion
    for report in task.progress_reports:
        if report.code == "purge.tasks.key.core.Task":
            if fuzzy:
                assert report.total >= expected
            else:
                assert report.total == expected
            break
    else:
        pytest.fail("NO core.Task DELETIONS?!?")


@pytest.fixture(scope="module")
def async_tasks_possible(pulp_settings):
    return (
        pulp_settings.UPLOAD_PROTECTION_TIME != 0
        or pulp_settings.TASK_PROTECTION_TIME != 0
        or pulp_settings.TMPFILE_PROTECTION_TIME != 0
    )


@pytest.fixture
def good_and_bad_task(
    pulpcore_bindings,
    dispatch_task,
    monitor_task,
    async_tasks_possible,
):
    pre_total, pre_final, pre_summary = _task_summary(pulpcore_bindings)

    # good task
    good_task = monitor_task(dispatch_task("pulpcore.app.tasks.test.sleep", args=(0,)))
    assert good_task.state == "completed"

    # bad sync
    bad_task_href = dispatch_task("pulpcore.app.tasks.test.sleep", args=(-1,))
    with pytest.raises(PulpTaskError):
        monitor_task(bad_task_href)
    bad_task = pulpcore_bindings.TasksApi.read(bad_task_href)
    assert bad_task.state == "failed"

    post_total, post_final, post_summary = _task_summary(pulpcore_bindings)
    if async_tasks_possible:
        assert post_total >= (pre_total + 2)
        assert post_final >= (pre_final + 2)
    else:
        assert post_total == (pre_total + 2)
        assert post_final == (pre_final + 2)

    return good_task, bad_task, pre_total, pre_final, pre_summary


def test_purge_before_time(pulpcore_bindings, good_and_bad_task, monitor_task):
    """Purge that should find no tasks to delete."""
    _, _, pre_total, _, _ = good_and_bad_task
    dta = Purge(finished_before="1970-01-01T00:00")
    response = pulpcore_bindings.TasksApi.purge(dta)
    task = monitor_task(response.task)
    new_total, new_final, new_summary = _task_summary(pulpcore_bindings)
    # Should have all tasks remaining (2 completed, 1 failed)
    assert (pre_total + 3) == new_total
    # Should show we report having purged no tasks
    assert _purge_report_total(task) == 0


def test_purge_defaults(pulpcore_bindings, good_and_bad_task, monitor_task):
    """Purge using defaults (finished_before=30-days-ago, state=completed)"""
    dta = Purge()
    response = pulpcore_bindings.TasksApi.purge(dta)
    monitor_task(response.task)

    good_task, bad_task, _, _, _ = good_and_bad_task
    # default is "completed before 30 days ago" - so both sync tasks should still exist
    # Make sure good sync-task still exists
    pulpcore_bindings.TasksApi.read(good_task.pulp_href)

    # Make sure the failed sync still exists
    pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_purge_all(pulpcore_bindings, good_and_bad_task, monitor_task, async_tasks_possible):
    """Purge all tasks in any 'final' state."""
    good_task, bad_task, pre_total, pre_final, pre_summary = good_and_bad_task

    states = list(TASK_FINAL_STATES)
    dta = Purge(finished_before=TOMORROW_STR, states=states)
    response = pulpcore_bindings.TasksApi.purge(dta)
    task = monitor_task(response.task)
    new_total, new_final, new_summary = _task_summary(pulpcore_bindings)
    assert 1 == new_final, "The purge-task should be the only final-task left"

    # Make sure good sync-task is gone
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(good_task.pulp_href)

    # Make sure failed sync-task is gone
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(bad_task.pulp_href)

    # Make sure we reported the deletions
    _check_delete_report(task, pre_final + 2, async_tasks_possible)


def test_purge_leave_one(pulpcore_bindings, good_and_bad_task, monitor_task, async_tasks_possible):
    """Arrange to leave one task unscathed."""
    # Leave only the failed sync
    good_task, bad_task, pre_total, pre_final, pre_summary = good_and_bad_task

    dta = Purge(finished_before=bad_task.finished_at)
    response = pulpcore_bindings.TasksApi.purge(dta)
    task = monitor_task(response.task)

    # Make sure good task is gone
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(good_task.pulp_href)

    # Make sure the bad task still exists
    pulpcore_bindings.TasksApi.read(bad_task.pulp_href)

    # Make sure we reported the task-deletion
    _check_delete_report(task, pre_final + 1, async_tasks_possible)


def test_purge_only_failed(pulpcore_bindings, good_and_bad_task, monitor_task):
    """Purge all failed tasks only."""
    dta = Purge(finished_before=TOMORROW_STR, states=["failed"])
    response = pulpcore_bindings.TasksApi.purge(dta)
    monitor_task(response.task)
    # good task should exist
    good_task, bad_task, pre_total, pre_final, pre_summary = good_and_bad_task
    pulpcore_bindings.TasksApi.read(good_task.pulp_href)

    # bad task should not exist
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(bad_task.pulp_href)


def test_bad_date(pulpcore_bindings, good_and_bad_task):
    """What happens if you use a bad date format?"""
    dta = Purge(finished_before="THISISNOTADATE")
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.purge(dta)


def test_bad_state(pulpcore_bindings, good_and_bad_task):
    """What happens if you specify junk for a state?"""
    dta = Purge(finished_before=TOMORROW_STR, states=["BAD STATE"])
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.purge(dta)


def test_not_final_state(pulpcore_bindings, good_and_bad_task):
    """What happens if you use a valid state that isn't a 'final' one?"""
    dta = Purge(finished_before=TOMORROW_STR, states=["running"])
    with pytest.raises(ApiException):
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
    admin_sync_data = RepositorySyncURL(remote=admin_remote.pulp_href)
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
        user_sync_data = RepositorySyncURL(remote=user_remote.pulp_href)
        user_repo = file_repository_factory()

    # Sync as admin
    sync_response = file_bindings.RepositoriesFileApi.sync(admin_repo.pulp_href, admin_sync_data)
    monitor_task(sync_response.task)

    # Purge as user
    states = list(TASK_FINAL_STATES)
    data = Purge(finished_before=TOMORROW_STR, states=states)
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
    data = Purge(finished_before=TOMORROW_STR, states=states)
    with user:
        response = pulpcore_bindings.TasksApi.purge(data)
        monitor_task(response.task)

    # Make sure task DOES NOT exist
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(sync_task.pulp_href)

    # Sync as user
    with user:
        sync_response = file_bindings.RepositoriesFileApi.sync(user_repo.pulp_href, user_sync_data)
        monitor_task(sync_response.task)

    # Purge as ADMIN
    states = list(TASK_FINAL_STATES)
    data = Purge(finished_before=TOMORROW_STR, states=states)
    response = pulpcore_bindings.TasksApi.purge(data)
    monitor_task(response.task)

    # Make sure task DOES NOT exist
    with pytest.raises(ApiException):
        pulpcore_bindings.TasksApi.read(sync_task.pulp_href)
