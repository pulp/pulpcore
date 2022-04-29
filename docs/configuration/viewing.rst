.. _viewing-settings:

Viewing Settings
================

To list the effective settings on a Pulp installation, while on the system where Pulp is installed
run the command ``dynaconf list``. This will show the effective settings Pulp will use.

.. note::

    Settings can come from both settings file and environment variables. When running the
    ``dynaconf list`` command, be sure you have the same environment variables set as your Pulp
    installation.

.. note::

    For the ``dynaconf list`` command to succeed it needs to environment variable set identifying
    where the django settings file is. ``export DJANGO_SETTINGS_MODULE=pulpcore.app.settings``.
