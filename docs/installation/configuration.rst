Configuration
=============

.. _configuration:

-----------

Pulp uses `dynaconf <https://dynaconf.readthedocs.io/en/latest/>`_ for its settings. dynaconf
allows storing `settings in multiple file formats <https://dynaconf.readthedocs
.io/en/latest/guides/examples.html>`_. By default Pulp looks for settings in ``/etc/pulp/settings
.py``. An alternate location for the settings file is specified by setting the ``PULP_SETTINGS``
environment variable. Each of the settings can also be set by prepending ``PULP_`` to the name
and setting it as an environment variable. The comprehensive list of settings can be found in
`Django docs <https://docs.djangoproject.com/en/2.1/ref/settings/>`_. `Environment variables
<https://dynaconf.readthedocs.io/en/latest/guides/environment_variables
.html#environment-variables>`_ take precedence over all other configuration sources. `TOML inline
table notation <https://github.com/toml-lang/toml#inline-table>`_ should be used to express any
nested environment variables such as ``PULP_LOGGING`` or ``PULP_DATABASES``. Python is the
recommended language for expressing configuration in a settings file.

SECRET_KEY
^^^^^^^^^^

    In order to get a pulp server up and running a `Django SECRET_KEY
    <https://docs.djangoproject.com/en/2.1/ref/settings/#secret-key>`_ *must* be
    provided.

    The following code snippet can be used to generate a random SECRET_KEY.

.. code-block:: python
   :linenos:

   import random

   chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
   print(''.join(random.choice(chars) for i in range(50)))

DATABASES
^^^^^^^^^

   By default Pulp uses PostgreSQL on localhost. For all possible configurations please refer to
   `Django documentation on databases <https://docs.djangoproject.com/en/2
   .1/ref/settings/#databases>`_

DEFAULT_FILE_STORAGE
^^^^^^^^^^^^^^^^^^^^

   By default, Pulp uses the local filesystem to store files. The default option which
   uses the local filesystem is ``pulpcore.app.models.storage.FileSystem``.

   This can be configured though to alternatively use `Amazon S3 <https://aws.amazon.com/s3/>`_. To
   use S3, set ``DEFAULT_FILE_STORAGE`` to ``storages.backends.s3boto3.S3Boto3Storage``. For more
   information about different Pulp storage options, see the :ref:`storage documentation <storage>`.

MEDIA_ROOT
^^^^^^^^^^

   The location where Pulp will store files. By default this is `/var/lib/pulp/`.

   If you're using S3, point this to the path in your bucket you want to save files. See the
   :ref:`storage documentation <storage>` for more info.

LOGGING
^^^^^^^

   By default Pulp logs at an INFO level to syslog. For all possible configurations please
   refer to `Django documenation on logging <https://docs.djangoproject.com/en/2
   .1/topics/logging/#configuring-logging>`_.

WORKING_DIRECTORY
^^^^^^^^^^^^^^^^^

   The directory used by workers to store files temporarily. This defaults to
   ``/var/lib/pulp/tmp/``.


REDIS_HOST
^^^^^^^^^^

   The hostname for Redis. By default Pulp will try to connect to Redis on localhost. `RQ
   documentation <https://python-rq.org/docs/workers/>`_ contains other Redis settings
   supported by RQ.

REDIS_PORT
^^^^^^^^^^

   The port for Redis. By default Pulp will try to connect to Redis on port 6380.

REDIS_PASSWORD
^^^^^^^^^^^^^^

   The password for Redis.


CONTENT_HOST
^^^^^^^^^^^^

   A string containing the protocol, fqdn, and port where the content app is deployed. This is used
   when Pulp needs to refer the client to the content serving app from within the REST API, such as
   the ``base_path`` attribute for a :term:`distribution`.

   This defaults to ``None`` which returns relative urls.


CONTENT_PATH_PREFIX
^^^^^^^^^^^^^^^^^^^

   A string containing the path prefix for the content app. This is used by the REST API when
   forming URLs to refer clients to the content serving app, and by the content serving application
   to match incoming URLs.

   Defaults to ``'/pulp/content/'``.


PROFILE_STAGES_API
^^^^^^^^^^^^^^^^^^

   A debugging feature that collects profile data about the Stages API as it runs. See
   staging api profiling docs for more information.
