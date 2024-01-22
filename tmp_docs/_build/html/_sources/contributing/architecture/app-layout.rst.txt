Pulp Platform Application Layout
================================

The Pulp Platform is built using two key frameworks, the Django Web Framework
and the Django REST Framework. Where possible, conforming to the conventions
of these frameworks is encouraged. The Pulp Platform strives to leverage these
frameworks as much as possible, ideally making Pulp Platform development a
work of implementation before innovation.

In the event that one of these components offers functionality that augments
or supersedes functionality in another component, the order of precedence of
these frameworks is:

* Pulp Platform
* Django REST Framework (DRF)
* Django Web Framework (Django)

So, features provided by the Pulp Platform should preferred over similar
features provided by DRF, and features in DRF should be preferred over similar
features provided by Django.


Module Layout
-------------

This is the basic layout of the ``pulpcore.app`` package, on the filesystem::

    pulpcore
    ├── app
    │   ├── apps.py
    │   ├── fields.py
    │   ├── __init__.py
    │   ├── logs.py
    │   ├── management
    │   │   ├── commands
    │   │   │   ├── __init__.py
    │   │   │   └── ...
    │   │   └── __init__.py
    │   ├── manage.py
    │   ├── migrations
    │   ├── models
    │   │   ├── __init__.py
    │   │   └── ...
    │   ├── pagination.py
    │   ├── response.py
    │   ├── serializers
    │   │   ├── __init__.py
    │   │   └── ...
    │   ├── settings.py
    │   ├── tasks
    │   │   ├── __init__.py
    │   │   └── ...
    │   ├── templates
    │   │   └── ...
    │   ├── tests
    │   │   └── ...
    │   ├── urls.py
    │   ├── viewsets
    │   │   ├── __init__.py
    │   │   └── ...
    │   └── wsgi.py
    └── __init__.py


The contents of this package are documented in detail in the :doc:`../platform-api/index`
documentation. Details how this package is organized can be found
below, along with information about some of the modules found in this namespace.

.. tip::

    This tree is incomplete, and maybe be out of date. Only the most notable and
    durable modules have been listed; the most complete listing of modules in this
    namespace will always be the :doc:`../platform-api/index` documentation.


Module Imports
--------------

For modules in the ``pulpcore.app`` namespace that are large and capture behaviors
across multiple concerns of pulp, such as our models, we have separated these
packages into subpackages. All public identifiers and objects defined
in submodules are then collected into that module's ``__init__.py``, from which
they will be imported by other Pulp Platform modules.

Using :mod:``pulpcore.app.models`` as an example, this means that when breaking up the
``models`` package in ``pulpcore.app``, the following things are true:

* No models are defined in the ``__init__.py`` of ``pulpcore.app.models``.
* All models are defined in submodules located in the ``pulpcore.app.models`` module
  directory (where its ``__init__.py`` can be found).
* The `__init__.py`` in ``pulpcore.app.models`` should consist only of import statements,
  ordered to prevent any circular import issues that may result based on the imports
  that are done in any included submodules.
* Any models defined in submodules in ``pulpcore.app.models`` namespace must be imported
  from the ``pulpcore.app.models`` namespace, not the submodule in which they are defined.
  Yes: ``from pulpcore.app.models import PulpModel``,
  No: ``from pulpcore.app.models.pulp import PulpModel``.
* When adding new models, they must be imported into the ``pulpcore.app.models``
  ``__init__.py``, so that they are available to be imported by any other Pulp Platform
  components that use them from the ``pulpcore.app.models`` namespace.
* Imports done inside any submodules should be relative, e.g.
  ``from .submodule import identifier`` or ``from . import submodule``, avoiding the
  creation of circular imports.
* Imports done inside the module's ``__init__.py`` should be relative and explict, e.g.

  * Yes: ``from .submodule import identifier1, identifier2``
  * No: ``from submodule import identifier1, identifier2``
  * No: ``from .submodule import *``

Any module in ``pulpcore.app`` broken up in this way, such as
:mod:`pulpcore.app.serializers` or :mod:`pulpcore.app.viewsets`, should do so in such a way
that renders the implementation invisible to anyone importing from that module.

pulpcore.app
------------

pulpcore.app is the package containing the core Pulp Platform Django application.
This package contains all of the Pulp Platform models, serializers, and
viewsets required to assemble Pulp's REST API and underlying database.

pulpcore.app.apps
^^^^^^^^^^^^^^^^^

This module defines the :class:`~pulpcore.app.apps.PulpPluginAppConfig` base class
used by all Pulp plugins to identify themselves to the Pulp Platform as plugins.

This module also includes the :class:`~pulpcore.app.apps.PulpAppConfig` class which
is the Pulp Platform application config.

pulpcore.app.settings
^^^^^^^^^^^^^^^^^^^^^

This is the main settings module for the platform Django project, which puts together
all of the various Django applications that the Pulp Platform depends on to function,
as well as the Pulp Platform application itself and its plugins.

Many things are defined in here, including the database settings, logging configuration,
REST API settings, etc. This file also finds and registers Pulp plugins with the Pulp
Platform Django Project, using the ``pulpcore.plugin`` entry point.

In order to use django-related tools with the Pulp Platform, the platform must be installed,
and the ``DJANGO_SETTINGS_MODULE`` environment var must be set to
:mod:`pulpcore.app.settings`.

pulpcore.app.urls
^^^^^^^^^^^^^^^^^

This module contains the API :data:`~pulpcore.app.urls.root_router`, and is where all non-API
views (should we ever write any) are mapped to URLs.

pulpcore.app.models
^^^^^^^^^^^^^^^^^^^

All models are contained in :mod:`pulpcore.app.models`.

The Platform models are all importable directly from the ``pulpcore.app.models``
namespace. All Pulp models should subclass :mod:`pulpcore.app.models.Model`, or
one of its subclasses.

.. note::

    All models must exist in the pulpcore.app.models namespace in order to be
    recognized by Django and included in the Django ORM.

Master/Detail Models
********************

A few Pulp Platform models, including the Content model as well as
Remotes and Publishers, implement a strategy we refer to as "Master/Detail".
The Master/Detail strategy, as implemented in Pulp, allows us to define
necessary relationships on a single master Model, while still allowing
plugin developers to extend these Master classes with details pertinent
to the plugin's requirements. Using the :class:`~pulpcore.app.models.Content`
model as an example, :class:`~pulpcore.app.models.Repository` relates to the
Content model. This causes all content to relate to the repositories that
contain them the same way while still allowing plugin writers to add any
additional fields or behaviors to the model as-needed for their use cases.

In the Pulp Platform, models requiring this sort of behavior should subclass
:class:`pulpcore.app.models.MasterModel`.


Serializers, ViewSets, and other Model-Related Classes
------------------------------------------------------

The modules containing Serializers and ViewSets, located in ``pulpcore.app.serializers`` and
``pulpcore.app.viewsets``, respectively, should be organized similarly to the models that
they represent where possible. For example, if ``pulpcore.app.models.Repository`` is defined
in the ``pulpcore.app.models.repository`` module, its corresponding serializer should be
defined in ``pulpcore.app.serializers.repository``, and its corresponding viewset should be
defined in ``pulpcore.app.viewsets.repository``, making it easy to find.

These, and other model-related classes, should be named in such a way as to make their
relationship to their Model unambiguous. To that end, model-related classes should include
the name of the model class they're related to in their name. So, the serializer for the
``pulpcore.app.models.Repository`` model should be named ``RepositorySerializer``, and the viewset
related to that model should be named ``RepositoryViewSet``.

Classes not directly related to a model, or related to multiple models, should still of
course be named in such a way as to make their purpose obvious an unambiguous.

ViewSet Registration
^^^^^^^^^^^^^^^^^^^^

In order for ViewSets to be automatically registered with the Pulp Platform API router,
they *must* subclass :class:`pulpcore.app.viewsets.base.NamedModelViewSet` and be imported into the
``pulpcore.app.viewsets`` namespace.

ViewSets not meeting this criteria must be manually registered with the API router in
:mod:`pulpcore.app.urls` by using the router's ``register`` method during application setup.
