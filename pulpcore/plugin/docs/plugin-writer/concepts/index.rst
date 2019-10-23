.. _plugin-concepts:

Plugin Concepts
===============

Like the Pulp Core itself, all Pulp Plugins are Django Applications, and could be created like any
other Django app with ``django-admin startapp <your_plugin>``. However, instead of writing all of
the boilerplate yourself, it is recommmended that you start your plugin by utilizing the `Plugin
Template <https://github.com/pulp/plugin_template>`_.  This guide will assume that you have used
the plugin_template, but if you are interested in the details of what it provides you, please see
:ref:`plugin-django-application` for more information for how plugins are "discovered" and connected to
the ``pulpcore`` Django app. Additional information is given as inline comments in the template.


Plugin API Usage
----------------
Plugin Applications interact with pulpcore with two high level interfaces, **subclassing** and
adding **tasks**. Additionally, plugins that need to implement dynamic web APIs can
optionally provide their own Django views. See our :ref:`live-apis` page for more information.


.. _subclassing-general:

Subclassing
-----------

Pulp Core and each plugin utilize `Django <https://docs.djangoproject.com/>`_ and the `Django Rest
Framework <https://www.django-rest-framework.org/>`_. Each plugin provides
:ref:`subclassing-models`, :ref:`subclassing-serializers`, and :ref:`subclassing-viewsets`. For
each object that a plugin writer needs to make, the ``pulpcore-plugin`` API provides base classes.
These base classes handle most of the boilerplate code, resulting in CRUD for each object out of
the box.

.. toctree::
   :maxdepth: 2

   subclassing/models
   subclassing/serializers
   subclassing/viewsets


.. _writing-tasks:

Tasks
-----

Any action that can run for a long time should be an asynchronous task. Plugin writers do not need
to understand the internals of the pulpcore tasking system, workers automatically execute tasks from
RQ, including tasks deployed by plugins.

**Reservations**

The tasking system adds a concept called **reservations** which ensures that actions that act on the
same resources are not run at the same time. To ensure data correctness, any action that alters the
content of a repository (thus creating a new version) must be run asynchronously, locking on the
repository and any other models which cannot change during the action. For example, sync tasks must
be asynchronous and lock on the repository and the remote. Publish should lock on the repository
version being published as well as the publisher.

**Deploying Tasks**

Tasks are deployed from Views or Viewsets, please see :ref:`kick-off-tasks`.

.. toctree::
   :maxdepth: 2

   tasks/add-remove
   tasks/publish
   tasks/export


Sync Pipeline
-------------

.. toctree::
   :maxdepth: 2

   sync_pipeline/sync_pipeline


Content Protection
------------------

Users can configure a ``ContentGuard`` to protect a ``Distribution`` on their own, but some plugins
want to offer built-in content protection features. For example pulp_docker may only want a user to
download docker images they have rights to based on some permissions system pulp_docker could
provide.

For more information see the :ref:`ContentGuard Usage by Plugin Writers
<plugin-writers-use-content-protection>` documentation.


Plugin Settings
---------------

Plugins can define settings by creating a ``<your plugin>.app.settings`` module containing settings
as you would define in the Django Settings File itself. ``pulpcore`` ships the actual settings.py
file so settings cannot be added directly as with most Django deployments. Instead as each plugin is
loaded, pulpcore looks for the ``<your plugin>.app.settings`` module and uses ``dynaconf`` to
overlay the settings on top of ``pulpcore``'s settings and user provided settings.

Settings are parsed in the following order with later settings overwriting earlier ones:

1. Settings from ``/etc/pulp/settings.py``.
2. Settings from ``pulpcore.app.settings`` (the pulpcore provided settings defaults).
3. Plugin settings from ``<your plugin>.app.settings``.

In some cases a setting should not overwrite an existing setting, but instead add to it. For
example, consider adding a custom log handler or logger to the `LOGGING <https://github.com/pulp/
pulpcore/blob/ec336c2b7bc7cefd3a28fc69dcd1c65655332841/pulpcore/app/settings.py#L183-L202>`_
settings. You don't want to fully overwrite it, but instead add or overwrite only a sub-portion.
``dynaconf`` provides the `dynaconf_merge feature <https://dynaconf.readthedocs.io/en/latest/guides/
usage.html#merging-existing-values>`_ which is for merging settings instead of overwriting them. For
example, pulp_ansible makes use of this `here <https://github.com/pulp/pulp_ansible/blob/
31dd6b77f0e2748644a4b76607be4a6cd2b6ce89/pulp_ansible/app/settings.py>`_.
