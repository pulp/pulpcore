.. _applying-settings:

Applying Settings
=================

Pulp uses `dynaconf <https://www.dynaconf.com/>`_ for its settings which allows you
to configure Pulp settings using various ways:


* :ref:`Environment Variables <env-var-settings>` - Enabled by default.

* :ref:`Configuration File <config-file-settings>` - Disabled by default, but easy to enable.
  Enabled by ``pulp_installer``.

.. _env-var-settings:

Environment Variables
---------------------

Configuration by specifying environment variables is enabled by default. Any
:ref:`Setting <settings>` can be configured using Dynaconf by prepending ``PULP_`` to the setting
name. For example :ref:`SECRET_KEY <secret-key-setting>` can be specified as the ``PULP_SECRET_KEY``
environment variable. For example, in a shell you can use ``export`` to set this::

    export PULP_SECRET_KEY="This should be a 50 chars or longer unique secret!"


.. _config-file-settings:

Configuration File
------------------

By default, Pulp does not read settings from a configuration file. Enable this by specifying the
``PULP_SETTINGS`` environment variable with the path to your configuration file. For example::

    export PULP_SETTINGS=/etc/pulp/settings.py

Then you can specify settings with Python variable assignment in the ``/etc/pulp/settings.py``. For
example, you can specify :ref:`SECRET_KEY <secret-key-setting>` with::

    $ cat /etc/pulp/settings.py
    SECRET_KEY="This should be a 50 chars or longer unique secret!"

In this example the settings file ends in ".py" so it needs to be valid Python, but it could use any
`dynaconf supported format <https://www.dynaconf.com/#supported-formats>`_.

.. note::

    The configuration file and directories containing the configuration file must be readable by the
    user Pulp runs as. If using SELinux, assign the ``system_u:object_r:pulpcore_etc_t:s0`` label.


.. _pulp-installer-settings:

pulp_installer
--------------

The `pulp_installer <https://docs.pulpproject.org/pulp_installer/>`_ enables configuration via a
settings file that lives at ``/etc/pulp/settings.py``. It does this by having each systemd file that
starts a Pulp service include::

    Environment="PULP_SETTINGS=/etc/pulp/settings.py"

A Pulp upgrade using ``pulp_installer`` will override the original ``/etc/pulp/settings.py``.
To keep your settings through an upgrade, use the "local settings" file located at
``/etc/pulp/settings.local.py`` which takes precedence over ``/etc/pulp/settings.py`` on a
setting-by-setting basis.
