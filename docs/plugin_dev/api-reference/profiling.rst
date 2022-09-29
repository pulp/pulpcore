.. _stages-api-profiling-docs:

Profiling the Stages API Performance
====================================

Pulp has a performance data collection feature that collects statistics about a Stages API pipeline
as it runs. The data is recorded to a sqlite3 database in the ``/var/lib/pulp/debug`` directory.

The feature can be activated by declaring the setting ``PROFILE_STAGES_API=True`` in the settings
file. Once enabled, Pulp will record the statistics with the UUID of the task name it runs.

Summarizing Performance Data
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

`pulpcore-manager` includes command that displays the pipeline along with summary statistics. After
generating a sqlite3 performance database, use the `stage-profile-summary` command like this::

   $ pulpcore-manager stage-profile-summary /var/lib/pulp/debug/2dcaf53a-4b0f-4b42-82ea-d2d68f1786b0


Profiling API Machinery
^^^^^^^^^^^^^^^^^^^^^^^

.. autoclass:: pulpcore.plugin.stages.ProfilingQueue

.. automethod:: pulpcore.plugin.stages.create_profile_db_and_connection
