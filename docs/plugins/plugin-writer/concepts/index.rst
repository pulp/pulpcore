.. _plugin-concepts:

Plugin Concepts
===============

Like the Pulp Core itself, all Pulp Plugins are Django Applications, and could be created like any
other Django app with ``pulpcore-manager startapp <your_plugin>``. However, instead of writing all
of the boilerplate yourself, it is recommmended that you start your plugin by utilizing the `Plugin
Template <https://github.com/pulp/plugin_template>`_.  This guide will assume that you have used
the plugin_template, but if you are interested in the details of what it provides you, please see
:ref:`plugin-django-application` for more information for how plugins are "discovered" and connected to
the ``pulpcore`` Django app. Additional information is given as inline comments in the template.


Plugin API Usage
----------------
Plugin Applications interact with pulpcore with two high level interfaces, **subclassing** and
adding **tasks**.


.. _subclassing-general:

Subclassing
-----------

Pulp Core and each plugin utilize `Django <https://docs.djangoproject.com/>`_ and the `Django Rest
Framework <https://www.django-rest-framework.org/>`_. Each plugin provides
:ref:`subclassing-models`, :ref:`subclassing-serializers`, and :ref:`subclassing-viewsets`. For
each object that a plugin writer needs to make, the ``pulpcore.plugin`` API provides base classes.
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
want to offer built-in content protection features. For example pulp_container may only want a user
to download container images they have rights to based on some permissions system pulp_container could
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


.. _custom-url-routes:

Custom API URL Routes
---------------------

The `typical plugin viewsets <subclassing-viewsets>`_ are all suburls under ``/pulp/api/v3/``, but
some content types require additional urls outside of this area. For example pulp_ansible provides
the Galaxy API at ``/pulp_ansible/galaxy/``.

Place a urls.py that defines a ``urlpatterns`` at the root of your Python package, and the pulpcore
plugin loading code will append those urls to the url root. This allows your urls.py to be a typical
Django file. For example pulp_ansible uses a `urls.py defined here <https://github.com/pulp/
pulp_ansible/blob/master/pulp_ansible/app/urls.py>`_


.. _custom-content-app-routes:

Custom Content App Routes
-------------------------

The Content App may also require custom routes, for example `pulp_container <https://github.com/
pulp/pulp_container/blob/master/pulp_container/app/content.py>`_ defines some. Read more about how
to :ref:`customize the content app with custom routes <content-app-docs>`.


.. _configuring-reverse-proxy-custom-urls:

Configuring Reverse Proxy with Custom URLs
------------------------------------------

When a plugin requires either Pulp API or Pulp Content App custom urls, the reverse proxy, i.e.
either Nginx or Apache, need to receive extra configuration snippets to know which service to route
the custom URLs to.

A best practice is to document clearly the custom URL requirements your plugin needs. Although the
installer can automatically install plugin snippets, other environments, e.g. k8s or docker or
docker containers may still need to configure them manually. Having clear docs is a minimum.

You can ship webserver snippets as part of your Python package with three steps:

1. Create a python package named ``webserver_snippets`` directory inside your app, e.g.
``pulp_ansible.app.webserver_snippets``. Like all Python packages it will have an ``__init__.py``.

2. Create an ``nginx.conf`` and an ``apache.conf``, and the installer will symlink to the correct
one depending on which reverse proxy is installed. Please create both as the installer supports
both.

3. Create an entry in MANIFEST.in to have the packaged plugin include the ``apache.conf`` and
``nginx.conf`` files.

Here is an example in `pulp_ansible's webserver configs <https://github.com/pulp/pulp_ansible/tree/
master/pulp_ansible/app/webserver_snippets>`_.

For the ``nginx.conf`` you can use variables with the names ``pulp-api`` and ``pulp-content`` as the
location for the backend services. For example, to route the url ``/pulp_ansible/galaxy/`` to the
Pulp API you could have your ``nginx.conf`` contain::

    location /pulp_ansible/galaxy/ {
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        # we don't want nginx trying to do something clever with
        # redirects, we set the Host: header above already.
        proxy_redirect off;
        proxy_pass http://pulp-api;
    }

The Apache config provides variables containing the location of the Pulp Content App and the Pulp
API as ``pulp-api`` and ``pulp-content`` respectively. Below is an equivalent snippet to the one
above, only for Apache::

    ProxyPass /pulp_ansible/galaxy http://${pulp-api}/pulp_ansible/galaxy
    ProxyPassReverse /pulp_ansible/galaxy http://${pulp-api}/pulp_ansible/galaxy


For the MANIFEST.in entry, you'll likely want one like the example below which was taken from
`pulp_ansible's MANIFEST.in <https://github.com/pulp/pulp_ansible/blob/master/MANIFEST.in>`_::

   include pulp_ansible/app/webserver_snippets/*


.. _plugin_installation:

Installation
------------

It's recommended to use the `Pulp 3 Ansible Installer <https://github.com/pulp/pulp_installer
#pulp-3-ansible-installer>`_ to install your plugin. Generally you can do this by configuring
``pulp_install_plugins`` variable with your Python package's name. For example for ``pulp-file``::

    pulp_install_plugins:
      pulp-file: {}


.. _custom-installation-tasks:

Custom Installation Tasks
-------------------------

If your plugin requires any custom installation steps, we recommend using an
Ansible Role prior to Pulp installation.

The easiest way to add custom installation tasks is to follow the
`Ansible Galaxy guide <https://galaxy.ansible.com/docs/contributing/creating_role.html>`_
to create a new role with tasks that needs to be done and publish it on Ansible Galaxy.

Documentation will need to be added to the plugin installation instructions. See the
`RPM Plugin Documentation <https://pulp-rpm.readthedocs.io/en/latest/installation.html#
install-with-pulp-installer-recommended>`_ as an example.
