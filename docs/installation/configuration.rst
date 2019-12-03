.. _configuration:

Configuration
=============

Pulp uses `dynaconf <https://dynaconf.readthedocs.io/en/latest/>`_ for its settings which allows you
to configure Pulp in a few ways:


By Configuration File
---------------------

To configure Pulp by settings file, you must set the format and location of the config file by
specifying the ``PULP_SETTINGS`` environment variable. For example, if you wanted to use Python to
specify your configuration, and provide it at ``/etc/pulp/settings.py`` you could::

    export PULP_SETTINGS=/etc/pulp/settings.py


Or in a systemd file you could::

    Environment="PULP_SETTINGS=/etc/pulp/settings.py" as the Ansible Installer does.


Dynaconf supports `settings in multiple file formats <https://dynaconf.readthedocs.io/en/latest/
guides/examples.html>`_

This file should have permissions of:

* mode: 640
* owner: root
* group: pulp (the group of the account that pulp runs under)
* SELinux context: system_u:object_r:etc_t:s0

If it is in its own directory like ``/etc/pulp``, the directory should have permissions of:

* mode: 750
* owner: root
* group: pulp (the group of the account that pulp runs under)
* SELinux context: unconfined_u:object_r:etc_t:s0

By Environment Variables
------------------------

Many users specify their Pulp settings entirely by Environment Variables. Each of the settings can
be configured using Dynaconf by prepending ``PULP_`` to the name of the setting and specifying that
as an Environment Variable. For example the ``SECRET_KEY`` can be specified by exporting the
``PULP_SECRET_KEY`` variable.
