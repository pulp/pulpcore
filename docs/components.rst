.. _deployment:

Architecture
============

Pulp's architecture has three components to it: a REST API, a content serving application, and the
tasking system. Each component can be horizontally scaled for both high availability and/or
additional capacity for that part of the architecture.

.. image:: /static/architecture.png
    :align: center

REST API
--------

Pulp's REST API is a Django application that runs under any WSGI server. It serves the following
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


Distributed Tasking System
--------------------------

Pulp's tasking system consists of a single ``pulpcore-worker`` component consequently, and can be
scaled by increasing the number of worker processes to provide more concurrency. Each worker can
handle one task at a time, and idle workers will lookup waiting and ready tasks in a distributed
manner. If no ready tasks were found a worker enters a sleep state to be notified, once new tasks
are available or resources are released.  Workers auto-name and are auto-discovered, so they can be
started and stopped without notifying Pulp.

.. note::

   Pulp serializes tasks that are unsafe to run in parallel, e.g. a sync and publish operation on
   the same repo should not run in parallel. Generally tasks are serialized at the "resource" level, so
   if you start *N* workers you can process *N* repo sync/modify/publish operations concurrently.

All necessary information about tasks is stored in Pulp's Postgres database as a single source of
truth. In case your tasking system get's jammed, there is a guide to help :ref:debugging_tasks.

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
