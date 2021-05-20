Troubleshooting
===============

.. _debugging_tasks:

Debugging Tasks
---------------

In case your system gets stuck in the processing of pulp tasks, you might want to debug the tasking system.

Please always consider that your system might be in the process of dealing with long running tasks, and other tasks are rightfully waiting on their completion.

Query tasks with the CLI
------------------------

How many tasks are waiting?

.. code-block:: bash

    pulp task list --state=waiting | jq 'length'

Is anybody running?

.. code-block:: bash

    pulp task list --state=running | jq 'length'

How many have failed?

.. code-block:: bash

    pulp task list --state=failed | jq 'length'

Retrieve the HREF's of running tasks:

.. code-block:: bash

    pulp task list --state=running | jq 'map({.name, .pulp_href})'
    # Save the HREF of the 3rd (counting starts at zero)
    TASK_HREF=$(pulp task list --state=running | jq -r 'map(.pulp_href)[3]')

Show the state of a particular task:

.. code-block:: bash

    pulp task show --href "$TASK_HREF"

Cancel a running task:

.. code-block:: bash

    # warning canceling tasks may break higher level workflows
    pulp task cancel --href "$TASK_HREF"

Deeper Inspection
-----------------

This requires root access on the pulp server.

Gather status information about the underlying ``rq`` service:

.. code-block:: bash

    rq info

A sample output can look like this:

.. code-block:: bash

    resource-manager | 0
    84459@pulp3.example.com | 0
    72284@pulp3.example.com | 0
    84635@pulp3.example.com | 0
    7 queues, 0 jobs total

    resource-manager (None None): ?
    84635@pulp3.example.com (None None): ?
    2 workers, 7 queues

    Updated: 2020-03-17 14:08:41.961447

There should at least be one queue for every worker.
The numbers behind the queues show the count of queued rq jobs.
If jobs pile up on the resource-manager queue, it's a sign that something might have got stuck.
In case you cannot resolve the issue, be sure to include the dump of this command with the issue description.

Find and Remove Stuck ``ReservedResource``
------------------------------------------

This requires root access on the pulp server.

In case the automatically scheduled resource cleanup job of a task was not properly executed, some resources can be stuck in a locked state.
They need to be removed by hand.

The following operations are meant to be executed inside Pulp's Django shell `pulpcore-manager shell`.
Be careful with running those commands, as they are executed without any protection in the python context of the Pulp application
If you choose to go down that road, you are on your own.

.. code-block:: python

    from pulpcore.app.models import Worker, ReservedResource

    # Are there missing workers?
    missing_workers = Worker.objects.missing_workers()
    missing_workers.count()

    # Look for resources that are hold by workers not considered online
    online_workers = Worker.objects.online_workers()
    zombies = ReservedResource.objects.exclude(worker__in=online_workers)
    zombies.count()

    # Dangerous action: Delete the zombie resources
    zombies.delete()
