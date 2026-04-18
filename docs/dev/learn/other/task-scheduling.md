

# Task Scheduling

% warning: This feature is only accessible by direct manipulation of
% ``TaskSchedule`` objects. It is targeted for plugin writers and no api access is planned.

Pulp supports scheduling of tasks. Scheduled tasks will be dispatched shortly after their
`next_dispatch` time, and be rescheduled one `dispatch_interval` after that, if the latter is
set. By specifying the `dispatch_interval` as `time_delta(days=1)` you can expect the task
dispatch to stabily happen at same time every day. Until the last task of the same schedule enters a
final state, a new task will not be dispatched. Scheduling is done by the worker processes,
therefore scheduled task dispatching will be missed if all workers are offline. After an outage
window, overdue schedules will dispatch at most one task, but down to timing, they may be
rescheduled shortly thereafter. The task schedule API at `/pulp/api/v3/task-schedules/` is
provided to read the tasks schedules.

## Passing Arguments to Scheduled Tasks

The `task_args` and `task_kwargs` fields on `TaskSchedule` allow plugin writers to store positional
and keyword arguments that will be forwarded to the task function each time it is dispatched. This
is useful when a scheduled task needs to operate on a specific resource or with specific options.

```python
from datetime import timedelta
from pulpcore.plugin.models import TaskSchedule

TaskSchedule(
    name="my-plugin-sync-schedule",
    task_name="my_plugin.app.tasks.sync",
    task_kwargs={"remote_pk": str(remote.pk), "optimize": True},
    dispatch_interval=timedelta(hours=6),
).save()
```

The args and kwargs stored in `task_args` and `task_kwargs` are passed directly
to `dispatch()` when the schedule fires, so they should match the signature of
the task function referenced by `task_name`. Both fields are encrypted at rest
(they will not be included in API responses).
