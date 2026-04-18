Added `task_args` and `task_kwargs` fields to `TaskSchedule`, allowing plugins to store positional
and keyword arguments that are forwarded to tasks when they are dispatched on schedule. Both fields
are encrypted at rest. `TaskSchedule` and `TaskScheduleSerializer` are now exposed via the plugin
API.
