.. _rq: http://python-rq.org


.. _deployment:

Architecture and Deploying
==========================

Pulp's architecture has three components to it: a REST API, a content serving application, and the
tasking system. Each component can be horizontally scaled for both high availability and/or
additional capacity for that part of the architecture.

REST API
--------

Pulp's REST API is a Django application which runs under any WSGI server. It serves the following
things:

* The REST API hosted at ``/pulp/api/v3/``
* The browse-able documentation at ``/pulp/api/v3/docs/``
* Any viewsets or views provided by plugins
* Static content used by Django, e.g. images used by the browse-able API. This is not Pulp content.

.. note::

   A simple, but limited way to run the REST API as a standalone service using the built-in Django
   runserver. The ``pulpcore-manager`` command is ``manage.py`` configured with the
   ``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. Run the simple webserver with::

      $ pulpcore-manager runserver 24817

.. warning::
    Until Role-Based Access Control is added to Pulp, REST API is not safe for multi-user use.
    Sensitive credentials can be read by any user, e.g. ``Remote.password``, ``Remote.client_key``.

The REST API can be deployed with any any WSGI webserver like a normal Django application. See the
`Django deployment docs <https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/>`_ for more
information.

Content Serving Application
---------------------------

An aiohttp.server based application that serves content to clients. The content could be
:term:`Artifacts<Artifact>` already downloaded and saved in Pulp, or
:term:`on-demand content units<on-demand content>`. When serving
:term:`on-demand content units<on-demand content>` the downloading also happens from within this
component as well.

.. note::

   Pulp installs a script that lets you run the content serving app as a standalone service as
   follows:::

      $ pulp-content

The content serving application can be deployed like any aiohttp.server application. See the
`aiohttp Deployment docs <https://aiohttp.readthedocs.io/en/stable/deployment.html>`_ for more
information.


Tasking System
--------------

Pulp's tasking system has two components: a resource manager and workers, all of which are run using
`rq`_.

Worker
  Pulp workers perform most tasks "run" by the tasking system including long-running tasks like
  synchronize and short-running tasks like a Distribution update. Each worker handles one task at a
  time, and additional workers provide more concurrency. Workers auto-name and are auto-discovered,
  so they can be started and stopped without notifying Pulp.

Resource Manager
  A different type of Pulp worker that plays a coordinating role for the tasking system. You must
  run exactly one of these for Pulp to operate correctly. The ``resource-manager`` is identified by
  configuring using exactly the name ``resource-manager`` with the ``-n 'resource_manager'`` option.

  *N* ``resource-manager`` rq processes can be started with 1 being active and *N-1* being passive.
  The *N-1* will exit and should be configured to auto-relaunch with either systemd, supervisord, or
  k8s.

.. note::

   Pulp serializes tasks that are unsafe to run in parallel, e.g. a sync and publish operation on
   the same repo should not run in parallel. Generally tasks are serialized at the "repo" level, so
   if you start *N* workers you can process *N* repo sync/modify/publish operations concurrently.


Static Content
--------------

When browsing the REST API or the browsable documentation with a web browser, for a good experience,
you'll need static content to be served.

In Development
^^^^^^^^^^^^^^

If using the built-in Django webserver and your settings.yaml has ``DEBUG: True`` then static
content is automatically served for you.

In Production
^^^^^^^^^^^^^

Collect all of the static content into place using the ``collectstatic`` command. The
``pulpcore-manager`` command is ``manage.py`` configured with the
``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. Run ``collectstatic`` as follows::

    $ pulpcore-manager collectstatic


Hardware requirements
---------------------

.. note::

   This section is updated based on your feedback. Feel free to share what your experience is https://pulpproject.org/help/

.. note::

   These are empirical guidelines to give an idea how to estimate what you need. It hugely
   depends on the scale of the setup (how much content you need, how many repositories you plan
   to have), frequency (how often you run various tasks) and the workflows (which tasks you
   perform, which plugin you use) of each specific user.


CPU
***

CPU count is recommended to be equal to the number of pulp workers. It allows to perform N
repository operations concurrently. E.g. 2 CPUs, one can sync 2 repositories concurrently.

RAM
***

Out of all operations the highest memory consumption task is likely synchronization of a remote
repository. Publication can also be memory consuming, however it depends on the plugin.

For each worker, the suggestion is to plan on 1GB to 3GB. E.g. 4 workers would need 4GB to 12 GB
For the database, 1GB is likely enough.

The range for the workers is quite wide because it depends on the plugin. E.g. for RPM plugin, a
setup with 2 workers will require around 8GB to be able to sync large repositories. 4GB is
likely not enough for some repositories, especially if 2 workers both run sync tasks in parallel.

Disk
****

For disk size, it depends on how one is using Pulp and which storage is used.


Pulp behaviour
^^^^^^^^^^^^^^

 * Pulp de-duplicates content.
 * There are different policies for downloading content. It is possible not to store any content
   at all.
 * If plugin needs to generate metadata for a repository, it will be in the artifact storage,
   even if the download policy is configured not to save any content.
 * Pulp verifies downloaded artifact checksums locally and artifacts are downloaded/verified in
   parallel, so some local storage is needed, even if the download policy is configured not to save
   any content and an external storage, like S3, is used.

Empirical estimation
^^^^^^^^^^^^^^^^^^^^

 * If S3 is used as a backend for artifact storage, it is not required to have a large local
   storage. 30GB should be enough in the majority of cases.

 * If no content is planned to be stored in the artifact storage, aka only sync from
   remote source and only with the ``streamed`` policy, some storage needs to be allocated for
   metadata. It depends on the plugin, the size of a repository and the number of different
   publications. 5GB should be enough for medium-large installation.

 * If content is downloaded ``on_demand``, aka only packages that clients request from Pulp. A
   good estimation would be 30% of the whole repository size, including futher updates to the
   content. That the most common usage pattern. If clients use all the packages from a repository,
   it would use 100% of the repository size.

 * If all content needs to be downloaded, the size of all repositories together is needed.
   Since Pulp de-duplicates content, this calculation assumes that all repositories have unique
   content.

 * Any additional content, one plans to upload to or import into Pulp, needs to be counted as well.

 * DB size needs to be taken into account as well.

E.g. For syncing remote repositories with ``on_demand`` policy and using local storage, one
would need 50GB + 30% of size of all the repository content + the DB.

.. _filesystem-layout:

Filesystem Layout
-----------------

..note::
  Pulp will mostly automatically manage those directories for you.
  Only if you need to adjust permissions or security contexts and perform a manual installation,
  you need to prepare them accordingly.

A usual installation of pulp needs the following files and directories:

================================ ==========================================================================================================
File/Directory                   Usage
================================ ==========================================================================================================
`/etc/pulp/settings.py`          Pulp's configuration file; optional; see :ref:`configuration`
`/var/lib/pulp`                  Home directory of the pulp user
`/var/lib/pulp/artifact`         Uploaded Artifacts are stored here; they should only be served through the `pulp-content` app
`/var/lib/pulp/assets`           Statically served assets like stylesheets, javascript and html; needed for the browsable api
`/var/lib/pulp/pulpcore-selinux` Contains the compiled selinux-policy if `pulpcore-selinux` is installed
`/var/lib/pulp/pulpcore_static`  Empty directory used as the document root in the reverse proxy; used to prevent accidentally serving files
`/var/lib/pulp/tmp`              Used for working directories of pulp workers
`/var/lib/pulp/upload`           Storage for upload chunks and temporary files that need to be shared between processes
================================ ==========================================================================================================

..note::
  `/var/lib/pulp/media` will be empty in case a cloud storage is configured :ref:`storage`
