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

   The location where Pulp will store files. By default this is ``/var/lib/pulp/media``.

   If you're using S3, point this to the path in your bucket you want to save files. See the
   :ref:`storage documentation <storage>` for more info.

   It should have permissions of:

   * mode: 750
   * owner: pulp (the account that pulp runs under)
   * group: pulp (the group of the account that pulp runs under)
   * SELinux context: system_u:object_r:pulpcore_var_lib_t:s0

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

   * mode: 750
   * owner: pulp (the account that pulp runs under)
   * group: pulp (the group of the account that pulp runs under)
   * SELinux context: system_u:object_r:pulpcore_var_lib_t:s0

.. note::

    It is recommended that ``WORKING_DIRECTORY`` and ``MEDIA_ROOT`` exist on the same storage
    volume for performance reasons. Files are commonly staged in the ``WORKING_DIRECTORY`` and
    validated before being moved to their permanent home in ``MEDIA_ROOT``.

CHUNKED_UPLOAD_DIR
^^^^^^^^^^^^^^^^^^

   A relative path inside the DEPLOY_ROOT directory used exclusively for uploaded chunks. The
   uploaded chunks are stored in the default storage specified by ``DEFAULT_FILE_STORAGE``. This
   option allows users to customize the actual place where chunked uploads should be stored within
   the declared storage. The default, ``upload``, is sufficient for most use cases. A change to
   this setting only applies to uploads created after the change.

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

   Defaults to ``/pulp/content/``.


.. _content-app-ttl:

CONTENT_APP_TTL
^^^^^^^^^^^^^^^

   The number of seconds before a content app should be considered lost.

   Defaults to ``30`` seconds.


.. _pulp-cache:

CACHE_ENABLED
^^^^^^^^^^^^^^^^^^

   .. note:: This feature is provided as a tech-preview

   Store cached responses from the content app into Redis. This setting improves the performance
   of the content app under heavy load for similar requests. Defaults to ``True``.

   .. note::
     The entire response is not stored in the cache. Only the location of the file needed to
     recreate the response is stored. This reduces database queries and allows for many
     responses to be stored inside the cache.

CACHE_SETTINGS
^^^^^^^^^^^^^

   Dictionary with tunable settings for the cache:

   * ``EXPIRES_TTL`` - Number of seconds entries should stay in the cache before expiring.

   Defaults to ``600`` seconds.

   .. note::
     Set to ``None`` to have entries not expire.
     Content app responses are always invalidated when the backing distribution is updated.


.. _worker-ttl:

WORKER_TTL
^^^^^^^^^^

   The number of seconds before a worker should be considered lost.

   Defaults to ``30`` seconds.


.. _remote-user-environ-name:

REMOTE_USER_ENVIRON_NAME
^^^^^^^^^^^^^^^^^^^^^^^^

   The name of the WSGI environment variable to read for :ref:`webserver authentication
   <webserver-authentication>`.

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


.. _profile-stages-api:

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

    .. warning::
      Enforcement of this setting in ``pulpcore`` and various plugins is not fully in place. It is
      possible that checksums not in this list may still be used in various places. This banner will
      be removed when it is believed all ``pulpcore`` and plugin code fully enforces this setting.

    The list of content-checksums this pulp-instance is **allowed to use**. By default the following
    are used::

        ALLOWED_CONTENT_CHECKSUMS = ["sha224", "sha256", "sha384", "sha512"]

    The entire set of supported checksums are: ``md5``, ``sha1``, ``sha224``, ``sha256``,
    ``sha384``, and ``sha512``.

    .. warning::
      Due to its use as the primary content-identifier, "sha256" **IS REQUIRED**. Pulp will
      fail to start if ``"sha256"`` is not found in this set.

    Pulp can prohibit or allow checksums by setting the ALLOWED_CONTENT_CHECKSUMS setting.
    Changing this setting requires a few steps.

    First, before you change the setting, see how your Pulp instance will be impacted by this change by running:

    ``pulpcore-manager handle-artifact-checksums --report --checksums sha256,512``

    Adjust ``--checksums`` as comma separated list of checksums types to match your needs.

    .. note::
      If you already changed ``ALLOWED_CONTENT_CHECKSUMS`` in pulp settings you can leave out ``--checksums``,
      and the checksums will be parsed from Pulp settings.

    Before switching, any on-demand repos containing forbidden checksum digests needs to be synced with
    ``policy=immediate`` to populate missing allowed checksums. This can heavily impact your disk space.
    Alternatively, users can remove these offending repo versions followed by orphan cleanup.

    If you have artifacts that do not conform to your ALLOWED_CONTENT_CHECKSUMS setting, they need to be re-hashed.
    You can update them using:

    ``pulpcore-manager handle-artifact-checksums``

    .. warning::
      ``--report`` and ``--checksums`` arguments are tech-preview and may change in backwards
      incompatible ways in future releases.

    .. warning::
      If Pulp fails to start because forbidden checkums have been identified or required ones are
      missing, run ``pulpcore-manager handle-artifact-checksums`` command.


.. _use-non-rq-pulp-workers:

USE_NEW_WORKER_TYPE
^^^^^^^^^^^^^^^^^^^

    Pulp has a new distributed queueless tasking system which can be activated with this setting.
    If ``True``, the ``pulpcore-worker`` command will start workers of the new type.  If ``False``
    it will chainload into the traditional ``rq`` based system.  Also the ``pulpcore-api``
    processes will dispatch their tasks accordingly.  When changing this value, all ``pulpcore``
    (at least api and worker) processes must be restarted.

    .. note:: Before changing this value, all pending tasks should be finalized. It cannot be
       guaranteed that they translate properly.

       A safe way to switch from the old to the new system or the other way around consists of:

       1. Shutting down the api-workers ``systemctl stop pulpcore-api``
       2. Wait for all pending tasks to finish; check with

          .. code-block:: text

             pulpcore-manager shell -c 'from pulpcore.app.models import Task;
             print(Task.objects.filter(state__in=["running", "waiting", "canceling"]).count())'

       3. Flip the ``USE_NEW_WORKER_TYPE`` setting
       4. Restart the resource manager ``systemctl restart pulpcore-resource-manager``
       5. Restart all workers ``systemctl restart pulpcore-worker@*``
       6. Start the api-workers ``systemctl start pulpcore-api``


.. _allow_shared_resources:

ALLOW_SHARED_TASK_RESOURCES
^^^^^^^^^^^^^^^^^^^^^^^^^^^

    This option allows tasks to have a shared (read only) simultaneous access to some resources. It
    defaults to ``False``, but when set to ``True`` may improve tasking throughput.

    .. note:: This option will only take effect when using the queueless worker type.

    .. note:: As a tech preview, this option is meant to be temporary. It will default to ``True``
              in 3.16 and be removed in 3.17.


.. _admin-site-url:

ADMIN_SITE_URL
^^^^^^^^^^^^^^

    The Django admin site URL. Defaults to ``admin/``.


.. _django-guid:

DJANGO_GUID
^^^^^^^^^^^

    Pulp uses ``django-guid`` to append correlation IDs to logging messages. Correlation IDs are
    autogenerated by default but can also be sent as a header with each request. They are also
    returned as a header in the response and are recorded in the ``logging_cid`` field of tasks.

    For more information on how to configure the ``DJANGO_GUID`` setting, see the `django-guid
    settings documentation <https://django-guid.readthedocs.io/en/latest/settings.html>`_.


.. _orphan-protection-time:

ORPHAN_PROTECTION_TIME
^^^^^^^^^^^^^^^^^^^^^^

    The time specified in minutes for how long Pulp will hold orphan Content and Artifacts before
    they become candidates for deletion by an orphan cleanup task. This should ideally be longer
    than your longest running task otherwise any content created during that task could be cleaned
    up before the task finishes. Default is 1440 minutes (24 hours).
