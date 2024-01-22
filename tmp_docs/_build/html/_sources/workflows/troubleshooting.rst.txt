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
