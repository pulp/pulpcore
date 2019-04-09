.. _runtests:

Testing pulp
============

There are two types of tests in *pulp_core* and in the plugins:

1. **Unittests** are meant to test the interface of a specific unit utilizing a test database.
2. **Functional tests** are meant to test certain workflows utilizing a running instance of pulp.

Prerequisites
-------------

If you want to run the functional tests, you need a running pulp instance that is allowed to be
mixed up by the tests.
For example, using the development vm (see :ref:`DevSetup`),
this can be accomplished by `workon pulp; django-admin runserver 24817`.
Also, you need a valid *pulp-smash*
`config <https://pulp-smash.readthedocs.io/en/latest/configuration.html>`_ file.
This can be created with `pulp-smash settings create`.

Running tests
-------------

In case pulp is installed in a virtual environment, activate it first (`workon pulp`).
All tests of a plugin are run with `django-admin test <plugin_name>`.
This involves setting up (and tearing down) the test database, however the functional tests are
still performed against the configured pulp instance with its *production* database.

To only perform the unittests, you can skip the prerequisites and call
`django-admin test <plugin_name>.tests.unit`.

If you are only interested in functional tests, you can skip the creation of the test database by
using `py.test <path_to_plugin>/<plugin_name>/tests/functional`.

.. note::

    Make sure, the task runners are actually running. In doubt, run `prestart` or
    `systemctl restart pulp-worker@*`.

.. note::

    You can be more specific on which tests to run by calling something like
    `django-admin test pulp_file.tests.unit.test_models` or
    `py.test <path_to_plugin>/<plugin_name>/tests/functional/api/test_sync.py`.
