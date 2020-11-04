.. _settings:

Settings
========

Pulp uses three types of settings:

* :ref:`Django settings <django-settings>` Pulp is configuring
* :ref:`RQ settings <rq-settings>` Pulp is using
* :ref:`Pulp defined settings <pulp-settings>`


.. _django-settings:

Django Settings
---------------

Pulp is a Django project, so any Django `Django setting
<https://docs.djangoproject.com/en/2.2/ref/settings/>`_ can also be set to configure your Pulp
deployment.

SECRET_KEY
^^^^^^^^^^

    In order to get a pulp server up and running a `Django SECRET_KEY
    <https://docs.djangoproject.com/en/2.2/ref/settings/#secret-key>`_ *must* be
    provided.

    The following code snippet can be used to generate a random SECRET_KEY.

.. code-block:: python
   :linenos:

   import random

   chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
   print(''.join(random.choice(chars) for i in range(50)))

DATABASES
^^^^^^^^^

   By default Pulp uses PostgreSQL on localhost. PostgreSQL is the only supported database. For
   instructions on how to configure the database, refer to :ref:`database installation <database-install>`.

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

   It should have permissions of:

   * mode: 750
   * owner: pulp (the account that pulp runs under)
   * group: pulp (the group of the account that pulp runs under)
   * SELinux context: system_u:object_r:var_lib_t:s0

LOGGING
^^^^^^^

   By default Pulp logs at an INFO level to syslog. For all possible configurations please
   refer to `Django documenation on logging <https://docs.djangoproject.com/en/2
   .2/topics/logging/#configuring-logging>`_.

AUTHENTICATION_BACKENDS
^^^^^^^^^^^^^^^^^^^^^^^

   By default, Pulp has two types of authentication enabled, and they fall back for each other:

   1. Basic Auth which is checked against an internal users database
   2. Webserver authentication that relies on the webserver to perform the authentication.

   To change the authentication types Pulp will use, modify the ``AUTHENTICATION_BACKENDS``
   settings. See the `Django authentication documentation <https://docs.djangoproject.com/en/2.2/
   topics/auth/customizing/#authentication-backends>`_ for more information.

.. _rq-settings:

RQ Settings
-----------

The following RQ settings can be set in your Pulp config:

  * REDIS_URL
  * REDIS_HOST
  * REDIS_PORT
  * REDIS_DB
  * REDIS_PASSWORD
  * SENTINEL

These will be used by any worker loaded with the ``-c 'pulpcore.rqconfig'`` option.

Below are some common settings used for RQ configuration. See the `RQ settings documentation
<http://python-rq.org/docs/workers/#using-a-config-file>`_ for information on these settings.

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


.. _pulp-settings:

Pulp Settings
-------------

Pulp defines the following settings itself:

WORKING_DIRECTORY
^^^^^^^^^^^^^^^^^

   The directory used by workers to stage files temporarily. This defaults to
   ``/var/lib/pulp/tmp/``.

   It should have permissions of:

   * mode: 755
   * owner: pulp (the account that pulp runs under)
   * group: pulp (the group of the account that pulp runs under)
   * SELinux context: unconfined_u:object_r:var_lib_t:s0

.. note::

    It is recommended that ``WORKING_DIRECTORY`` and ``MEDIA_ROOT`` exist on the same storage
    volume for performance reasons. Files are commonly staged in the ``WORKING_DIRECTORY`` and
    validated before being moved to their permanent home in ``MEDIA_ROOT``.

CHUNKED_UPLOAD_DIR
^^^^^^^^^^^^^^^^^^

   A directory used exclusively for uploaded chunks. The uploaded chunks are stored in the default
   storage specified by ``DEFAULT_FILE_STORAGE``. This option allows users to customize the actual
   place where chunked uploads should be stored within the declared storage.

CONTENT_ORIGIN
^^^^^^^^^^^^^^

   A required string containing the protocol, fqdn, and port where the content app is reachable by
   users. This is used by ``pulpcore`` and various plugins when referring users to the content app.
   For example if the API should refer users to content at using http to pulp.example.com on port
   24816, (the content default port), you would set: ``https://pulp.example.com:24816``.


.. _content-path-prefix:

CONTENT_PATH_PREFIX
^^^^^^^^^^^^^^^^^^^

   A string containing the path prefix for the content app. This is used by the REST API when
   forming URLs to refer clients to the content serving app, and by the content serving application
   to match incoming URLs.

   Defaults to ``'/pulp/content/'``.


.. _content-app-ttl:

CONTENT_APP_TTL
^^^^^^^^^^^^^^^

   The number of seconds before a content app should be considered lost.

   Defaults to ``30`` seconds.


.. _remote-user-environ-name:

REMOTE_USER_ENVIRON_NAME
^^^^^^^^^^^^^^^^^^^^^^^^

   The name of the WSGI environment variable to read for :ref:`webserver authentication
   <webserver-auth>`.

   .. warning::

      Configuring this has serious security implications. See the `Django warning at the end of this
      section in their docs <https://docs.djangoproject.com/en/2.2/howto/auth-remote-user/
      #configuration>`_ for more details.

   Defaults to ``'REMOTE_USER'``.


.. _allowed-import-paths:

ALLOWED_IMPORT_PATHS
^^^^^^^^^^^^^^^^^^^^

   One or more real filesystem paths that Remotes with filesystem paths can import from. For example
   to allow a remote url of ``file:///mnt/foo/bar/another/folder/`` you could specify::

       ALLOWED_IMPORT_PATHS = ['/mnt/foo/bar']  # only a subpath is needed

   Defaults to ``[]``, meaning ``file:///`` urls are not allowed in any Remote.

.. _allowed-export-paths:

ALLOWED_EXPORT_PATHS
^^^^^^^^^^^^^^^^^^^^

   One or more real filesystem paths that Exporters can export to. For example to allow a path of
   ``/mnt/foo/bar/another/folder/`` you could specify::

       ALLOWED_EXPORT_PATHS = ['/mnt/foo/bar']  # only a subpath is needed

   Defaults to ``[]`` which means no path is allowed.


PROFILE_STAGES_API
^^^^^^^^^^^^^^^^^^

   A debugging feature that collects profile data about the Stages API as it runs. See
   staging api profiling docs for more information.

   .. warning::

      Profiling stages is provided as a tech preview in Pulp 3.0. Functionality may not fully work
      and backwards compatibility when upgrading to future Pulp releases is not guaranteed.

.. _allowed-content-checksums:

ALLOWED_CONTENT_CHECKSUMS
^^^^^^^^^^^^^^^^^^^^^^^^^

    The list of content-checksums this pulp-instance is **allowed to use**. This list is a
    proper subset of the checksums defined by the Artifact model. You may safely list fewer
    algorithms than the Artifact model supports (although see the warning below regarding ``sha256``),
    but adding unknown algorithms will cause unexpected behavior.

    See :ref:`Configuration` for details on how to change configuration-options.

    .. warning::
      Due to its use as a primary content-identifier, "sha256"" **IS REQUIRED**. Pulp will
      fail to start if it is not found in this set.

    .. warning::
      Specifying checksums that are not available to models.Artifact will cause Pulp to fail to start.
      The complete set of supported checksum algorithms includes the following:

      ``{"md5", "sha1", "sha224", "sha256", "sha384", "sha512"}``

    .. warning::
      If Pulp fails to start because forbidden checkums have been identified or required ones are
      missing, run ``pulpcore-manager handle-artifact-checksums`` command. This command is in
      tech-preview and may change in backwards incompatible ways in future releases.

ADMIN_SITE_URL
^^^^^^^^^^^^^^

    The Django admin site URL. Defaults to ``admin/``.


DJANGO_GUID
^^^^^^^^^^^

    Pulp uses ``django-guid`` to append correlation IDs to logging messages. Correlation IDs are
    autogenerated by default but can also be sent as a header with each request. They are also
    returned as a header in the response and are recorded in the ``logging_cid`` field of tasks.

    For more information on how to configure the ``DJANGO_GUID`` setting, see the `django-guid
    settings documentation <https://django-guid.readthedocs.io/en/latest/settings.html>`_.

    This feature is provided as a tech preview and backwards incompatible changes may affect it in
    future releases of Pulp.
