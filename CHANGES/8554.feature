Added a ``/tasks/purge/`` API to do bulk-deletion of old tasks.

Over time, the database can fill with task-records. This API allows
an installation to bulk-remove records based on their completion
timestamps.

NOTE: this endpoint is in tech-preview and may change in backwards
incompatible ways in the future.
