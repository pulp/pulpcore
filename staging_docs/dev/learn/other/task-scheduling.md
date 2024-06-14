

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
