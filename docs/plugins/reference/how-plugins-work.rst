How Plugins Work
================

.. _plugin-django-application:

Plugin Django Application
-------------------------

Like the Pulp Core itself, all Pulp Plugins begin as Django Applications, started like any other
with `pulpcore-manager startapp <your_plugin>`. However, instead of subclassing Django's
`django.apps.AppConfig` as seen `in the Django documentation <https://docs.djangoproject.com/en/2.2
/ref/applications/#for-application-authors>`_, Pulp Plugins identify themselves as plugins to
pulpcore by subclassing :class:`pulpcore.plugin.PulpPluginAppConfig`.

:class:`pulpcore.plugin.PulpPluginAppConfig` also provides the application autoloading behaviors,
such as automatic registration of viewsets with the API router, which adds plugin endpoints.

The :class:`pulpcore.plugin.PulpPluginAppConfig` subclass for any plugin must set a few required
attributes:

* ``name`` attribute defines the importable dotted Python location of the plugin application (the
  Python namespace that contains at least models and viewsets).
* ``label`` attribute to something that unambiguously labels the plugin in a clear way for users.
  See `how it is done <https://github.com/pulp/pulp_file/blob/master/pulp_file/app/__init__.py>`_ in
  the ``pulp_file`` plugin.
* ``version`` attribute to the string representing the version.


.. _plugin-entry-point:

pulpcore.plugin Entry Point
---------------------------

The Pulp Core discovers available plugins by inspecting the pulpcore.plugin entry point.

Once a plugin has defined its :class:`pulpcore.plugin.PulpPluginAppConfig` subclass, it should add
a pointer to that subclass using the Django ``default_app_config`` convention, e.g.
``default_app_config = pulp_myplugin.app.MyPulpPluginAppConfig`` somewhere in the module that
contains your Django application. The Pulp Core can then be told to use this value to discover your
plugin, by pointing the pulpcore.plugin entry point at it. If, for example, we set
``default_app_config`` in ``pulp_myplugin/__init__.py``, the setup.py ``entry_points`` would look like
this:

.. code-block:: python

        entry_points={
            'pulpcore.plugin': [
                'pulp_myplugin = pulp_myplugin:default_app_config',
            ]
        }

If you do not wish to use Django's ``default_app_config`` convention, the name given to the
``pulpcore.plugin`` entry point must be an importable identifier with a string value containing the
importable dotted path to your plugin's application config class, just as ``default_app_config``
does.

Check out ``pulp_file`` plugin: `default_app_config
<https://github.com/pulp/pulp_file/blob/master/pulp_file/__init__.py>`_ and `setup.py example
<https://github.com/pulp/pulp_file/blob/master/setup.py>`_.


.. _mvs-discovery:

Model, Serializer, Viewset Discovery
------------------------------------

The structure of plugins should, where possible, mimic the layout of the Pulp Core Plugin API. For
example, model classes should be based on platform classes imported from
:mod:`pulpcore.plugin.models` and be defined in the `models` module or directory of a plugin app.
ViewSets should be imported from :mod:`pulpcore.plugin.viewsets`, and be defined in the `viewsets`
module of a plugin app, and so on.

This matching of module names is required for the Pulp Core to be able to auto-discover plugin
components, particularly for both models and viewsets.

Take a look at `the structure <https://github.com/pulp/pulp_file/tree/master/pulp_file/app>`_ of
the ``pulp_file`` plugin.


Serializer and OpenAPI schema
-----------------------------

Serializers are converted to OpenAPI objects through `drf-spectacular <https://github.com/tfranzel/drf-spectacular>`_.
It inspects all serializer fields to describe them in the OpenAPI schema.
Due to the `DRF issue <https://github.com/encode/django-rest-framework/issues/7354>`_
it is preferable to use ``CharField`` instead of ``URLField``.
Otherwise The REST API hosted at ``/pulp/api/v3/`` may hide some paths.

