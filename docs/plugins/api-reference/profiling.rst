.. _stages-api-profiling-docs:

Profiling the Stages API Performance
====================================

Pulp has a performance data collection feature that collects statistics about a Stages API pipeline
as it runs. The data is recorded to a sqlite3 database in the `/var/lib/pulp/debug` folder.

This can be enabled with the `PROFILE_STAGES_API = True` setting in the Pulp settings file. Once
enabled it will write a sqlite3 with the uuid of the task name it runs in to the
`/var/lib/pulp/debug/` folder.

Summarizing Performance Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`pulpcore-manager` includes command that displays the pipeline along with summary statistics. After
generating a sqlite3 performance database, use the `stage-profile-summary` command like this::

   $ pulpcore-manager stage-profile-summary /var/lib/pulp/debug/2dcaf53a-4b0f-4b42-82ea-d2d68f1786b0


Profiling API Machinery
^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.ProfilingQueue

.. automethod:: pulpcore.plugin.stages.create_profile_db_and_connection
