import pytest
import sys
from pulpcore.app.models import Task, ProgressReport
from pulpcore.constants import TASK_STATES


@pytest.mark.parametrize(
    "to_state,use_canceled",
    [
        (TASK_STATES.FAILED, False),
        (TASK_STATES.CANCELED, False),
        (TASK_STATES.CANCELED, True),
    ],
)
@pytest.mark.django_db
def test_report_state_changes(to_state, use_canceled):
    task = Task.objects.create(name="test", state=TASK_STATES.RUNNING)
    reports = {}
    for state in vars(TASK_STATES):
        report = ProgressReport(message="test", code="test", state=state, task=task)
        report.save()
        reports[state] = report

    if TASK_STATES.FAILED == to_state:
        # Two ways to fail a task - set_failed and set_canceled("failed")
        if use_canceled:
            task.set_cancelling()
            task.set_canceled(TASK_STATES.FAILED)
        else:
            try:
                raise ValueError("test")
            except ValueError:
                exc_type, exc, tb = sys.exc_info()
                task.set_failed(exc, tb)
    elif TASK_STATES.CANCELED == to_state:
        task.set_canceling()
        task.set_canceled()

    for state in vars(TASK_STATES):
        report = ProgressReport.objects.get(pk=reports[state].pulp_id)
        if TASK_STATES.RUNNING == state:  # report *was* running, should be changed
            assert to_state == report.state
        else:
            assert state == report.state
