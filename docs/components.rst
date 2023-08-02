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
`Django deployment docs <https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/>`_ for more
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


Availability
------------
Ensuring the REST API and the content server is healthy and alive:
* REST API: GET request to ``${API_ROOT}api/v3/status/`` see :ref:`API_ROOT <api-root>`
* Content Server: HEAD request to ``/pulp/content/`` or :ref:`CONTENT_PATH_PREFIX <content-path-prefix>`


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



.. _analytics:

Analytics Collection
--------------------

By default, Pulp installations post anonymous analytics data every 24 hours which is summarized on
`<https://analytics.pulpproject.org/>`_ and aids in project decision making. This is enabled by
default but can be disabled by setting ``ANALYTICS=False`` in your settings.

Here is the list of exactly what is collected along with an example below:

* The version of Pulp components installed as well as the used PostgreSQL server
* The number of worker processes and number of hosts (not hostnames) those workers run on
* The number of content app processes and number of hosts (not hostnames) those content apps run on
* The number of certain RBAC related entities in the system (users, groups, domains, custom roles,
  custom access policies)

.. note::

   We may add more analytics data points collected in the future. To keep our high standards for
   privacy protection, we have a rigorous approval process in place. You can see open proposals on
   `<https://github.com/pulp/analytics.pulpproject.org/issues>`_. In doubt,
   `reach out to us <https://pulpproject.org/get_involved/>`_.

An example payload:

.. code-block:: json

    {
        "systemId": "a6d91458-32e8-4528-b608-b2222ede994e",
        "onlineContentApps": {
            "processes": 2,
            "hosts": 1
        },
        "onlineWorkers": {
            "processes": 2,
            "hosts": 1
        },
        "components": [{
            "name": "core",
            "version": "3.21.0"
        }, {
            "name": "file",
            "version": "1.12.0"
        }],
        "postgresqlVersion": 90200
    }


.. _telemetry:

Telemetry Support
-----------------

Pulp can produce OpenTelemetry data, like the number of requests, active connections and latency response for
`pulp-api` using OpenTelemetry. You can read more about
`OpenTelemetry here <https://opentelemetry.io>`_.

If you are using `Pulp in One Container <https://pulpproject.org/pulp-in-one-container/>`_ or `Pulp Operator
<https://docs.pulpproject.org/pulp_operator/>`_ and want to enable it, you will need to set the following
environment variables:

* ``PULP_OTEL_ENABLED`` set to ``True``.
* ``OTEL_EXPORTER_OTLP_ENDPOINT`` set to the address of your OpenTelemetry Collector instance
  ex. ``http://otel-collector:4318``.
* ``OTEL_EXPORTER_OTLP_PROTOCOL`` set to ``http/protobuf``.

If you are using other type of installation maybe you will need to manually initialize Pulp using the
`OpenTelemetry automatic instrumentation
<https://opentelemetry.io/docs/instrumentation/python/getting-started/#instrumentation>`_
and set the following environment variables:

* ``OTEL_EXPORTER_OTLP_ENDPOINT`` set to the address of your OpenTelemetry Collector instance
  ex. ``http://otel-collector:4318``.
* ``OTEL_EXPORTER_OTLP_PROTOCOL`` set to ``http/protobuf``.

.. note::
  A quick example on how it would run using this method::

    $ /usr/local/bin/opentelemetry-instrument --service_name pulp-api /usr/local/bin/pulpcore-api \
    --bind "127.0.0.1:24817" --name pulp-api --workers 4 --access-logfile -

You will need to run an instance of OpenTelemetry Collector. You can read more about the `OpenTelemetry
Collector here <https://opentelemetry.io/docs/collector/>`_.
