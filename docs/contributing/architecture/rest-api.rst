REST API Guidelines
===================

Introduction
------------

The Pulp 3 API is intended to be decoupled from the data model, which the Django REST Framework
(DRF) makes it pretty easy to do. Where needed, support classes have been added to help the REST
API correctly and consistently represent our specialized models and relationships (most notably
the Master/Detail relationship).

Our API starts at a :term:`DRF` :term:`Router`. Each :term:`ViewSet` is attached to this
router, and the router's routes are exposed in urls.py. Subclasses of
:class:`pulpcore.app.viewsets.base.NamedModelViewSet` are automatically registered with the API router,
and most (possibly all) ViewSets created by plugins should be subclasses of this base class.
NamedModelViewSets are associated with a Django queryset, a :term:`Serializer` that is able to
represent members of the Django queryset in the API, and an endpoint name used when registering
the ViewSet with the API router.

All models exposed via the API must have a corresponding Serializer. Each NamedModelViewSet must
be related to a serializer and a queryset of model instances to serialize.

Since Serializers and ViewSets are so closely related to the models they represent, the
serializers and viewsets directories are laid out similarly to the models directory to help keep
things consistent and easy to find.

The API basic component tree looks like this::

    router
    |-- viewset
    |   |-- queryset
    |   |-- serializer
    |
    |-- viewset
    |   |-- ...
    |
    |-- ...

When creating API components, consider these guidelines:

* Where possible, API components representing models will be defined in files whose names match
  the corresponding file names of the models represented. For example, if you're defining the
  serializer for a model found in ``pulpcore.app.models.consumer``, the serializer should be defined in
  ``pulpcore.app.serializers.consumer``, and imported by name into ``pulpcore.app.serializers``.

* All objects represented in the REST API will be referred to by a single complete URL to that
  object, using a DRF ``HyperlinkedRelatedField`` or subclass. Non-hyperlinked relations (e.g.
  ``PrimaryKeyRelatedField``, ``SlugRelatedField``, etc) should be avoided. See the "Serializer
  Relationships" section below for more details. In the database an object is identified by its
  Primary Key. In the API an object is identified by its URL.

* :class:`pulpcore.app.viewsets.base.NamedModelViewSet` subclasses defined in a plugin's "viewsets" module
  are automatically registered with the API router. Endpoint names (the ``endpoint_name`` attribute)
  should plural, not singular (e.g. /pulp/api/v3/repositories/, not /pulp/api/v3/repository/).

* DRF supports natural keys on models in ModelViewSets with the "lookup_field" class attribute, but
  only if the natural key is derived from a single field (e.g. ``Repository.name``). For natural
  keys made up of multiple fields, a custom Viewset and Serializer are required. The custom ViewSet
  ensures that the correct URL endpoints are created, and that a model instance can be returned for
  a given natural key. The custom Serializer (and any necessary related serializer fields), at a
  minimum, ensures that objects generate the correct ``pulp_href`` value when serialized.


Serializer Relationships
------------------------

Serializer Notes
^^^^^^^^^^^^^^^^

* Many of the model writing guidelines can be applied to writing serializers. Familiarity with
  them is recommended for writers of serializers.

* All Serializers representing Pulp Models should subclass
  :class:`pulpcore.app.serializers.base.ModelSerializer`, as it provides useful behaviors to handle some
  of the conventions used when building Pulp Models.

* Whether serializer fields are explicitly declared on the serializer class or not, the field names
  to expose via the API must be declared by specifying 'fields' in the serializer's ``Meta`` class,
  as described in the DRF :term:`Serializer` docs. The names of exposed API fields should always
  be explicit.

* Serialized objects will provide thier own URL as the value of the "pulp_href" field on the serializer.
  You will need to use a ``rest_framework.serializers.HyperlinkedIdentifyField`` to generate the
  ``pulp_href`` field value by specifying its ``view_name``. If this object is referenced in the url by
  a field other than the pk, you will also need to specify a ``lookup_field``.

* When subclassing serializers, you should also explicitly inherit properties that would normally
  be overridden in the parent Serializer's Meta class.


Normal
^^^^^^

A "Normal" relationship, for the purposes of this document, is defined as a Model that relates
to another Model with no specialized models on either side.

"Specialized" models include Generic Relations or a relation to the "Detail" side of a Master/Detail
Model, and are documented below.

When relating a serializer to serializers representing other models (or lists of other models),
remember to use DRF's HyperlinkedRelatedField, or a subclass of it, to ensure the relationship
is represented by complete URLs. Since this is a normal thing to do, the DRF docs explain how
to do it in detail:

http://www.django-rest-framework.org/api-guide/relations/#hyperlinkedrelatedfield

To determine the 'view_name' to use when declaring a HyperlinkedRelatedField, it should be
be ``<endpoint_name>-<view_action>``, e.g. 'repositories-detail' when relating to a "normal" model
ViewSet whose ``endpoint_name`` is 'repositories'.

Nested
^^^^^^

Serializers can be nested inside other serializers, so in some cases it might make for a
better user experience to nest related objects inside their parent rather than only presenting
a list of links to related objects. When relating to "normal" models, this is also supported by
DRF out of the box, and the DRF docs explain how to do it in detail:

http://www.django-rest-framework.org/api-guide/relations/#nested-relationships

There are caveats to this when the nested relationship is intended to be writable. Mainly, DRF
needs to be told *how* it's supposed to validate and update nested objects. This is done by
implementing the create and update methods on the serializer that contains nested serializers,
as documented here:

http://www.django-rest-framework.org/api-guide/relations/#writable-nested-serializers

Nesting many read/write serializers may result in very complicated create/update methods, but
doing so potentially decreases the number of endpoints a user has to use when accessing the API,
which increases usability. The opposite is also true, in that too much nesting might hinder the
API usability, so the question of whether or not to nest a serializer should be handled case-by-
case.

An example of where this *might not* be useful is including complete Detail representations
of Content related to a Repository when viewing a Repository instance, since those instances
would have to be `cast()`, and there could literally be millions of them.

Master/Detail
^^^^^^^^^^^^^

The Master/Detail model relationships used in platform models is an internal detail that should be
invisible to the API user. "Master" models of the Master/Detail relationship should not be exposed
via the API.

"Detail" models, then, provide a bit of a challenge, because the API needs to ensure that it is
rendering the down-cast version of the model instance requested, or referencing the correct view
name of that model when using a related field.

This is enough of a tricky problem that it has its own section in the docs a little bit below,
called "Master/Detail Relationships Overview".

Building Explicit Serializers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In Pulp 3, the REST API will adhere to semantic versioning. This means that we need to exercise
control over what fields are exposed in the REST API, and that those fields are always exposed
the same way so that we don't break backward compatibility. To convert a ModelSerializer to its
explicit Serializer class, DRF provides an excellent bit of functionality::

    >>> from serializers import RepositorySerializer
    >>> RepositorySerializer()
    RepositorySerializer():
        pulp_href = HyperlinkedIdentityField(view_name='repositories-detail')
        name = CharField(style={'base_template': 'textarea.html'}, validators=[<UniqueValidator(queryset=Repository.objects.all())>])
        description = CharField(allow_blank=True, required=False, style={'base_template': 'textarea.html'})
        last_content_added = DateTimeField(allow_null=True, required=False)
        last_content_removed = DateTimeField(allow_null=True, required=False)
        content = HyperlinkedRelatedField(many=True, read_only=True, view_name='content-detail')

DRF Serializers fully support __repr__, which means calling repr() on them will return a string
that can be used to create that serializer. So, to see what fields DRF automatically generated
for a ModelSerializer, either instantiate it in an interpreter, or capture the output via repr()
and output it explicitly.


Master/Detail Relationships Overview
------------------------------------

The Master/Detail pattern that we're using in our Models requires some specific behaviors to
be properly implemented in the API. Care has been taken to expose the inner workings of these
behaviors to be easy to override or customize in plugins (if needed).

ViewSets
^^^^^^^^

As with most things related to the API, the place to start working with Master/Detail models
is in their ViewSet. The default ViewSet base class provided by the Pulp platform,
:class:`pulpcore.app.viewsets.base.NamedModelViewSet` is aware of Master/Detail relationships, and
will do the right thing when registered with our API router. In order to benefit from this
behavior, a ViewSet must be declared that represents the Master model of a Master/Detail
relationship, and that ViewSet must, at a minimum, have its ``endpoint_name`` set to something
reasonable for that master model. For example, the Master ViewSet representing the Content
Model should probably have its ``endpoint_name`` be set to "content".

All ViewSets representing Detail Models must subclass their respective Master ViewSet, and have
their ``endpoint_name`` set to a string that uniquely identifies them. The autogenerated API
endpoint for a Detail ViewSet will include both the master and detail ``endpoint_name``.
Building on the Content Model example, if we were making a ViewSet to represent the RPM
Detail Model, a reasonable ``endpoint_name`` would be "rpm". When combined with its Master
ViewSet, the generated endpoint would become ``content/rpm``.

If in doubt, the Master ViewSet's ``endpoint_name`` should be set to the Master Model's
plural verbose name (e.g. ``Content._meta.verbose_name_plural``, which is "content"), and
the Detail ViewSet's ``endpoint_name`` should be set to the Detail Model's TYPE value (e.g.
``RPM.TYPE``, which is probably ``RPM``). There generated endpoint for this detail ViewSet
example would then become ``content/rpm``.

Note that the Detail ViewSet's ``endpoint_name`` only needs to be unique among its Detail
ViewSet peers sharing the same Master ViewSet. It would be perfectly acceptable, for example,
to have a Detail Remote ViewSet with ``endpoint_name`` "rpm", since the generated endpoint
for that ViewSet would be something like ``remote/rpm``, and not conflict with any of the
endpoints generated for Detail ViewSets that share the Content Model as a Master.

Setting ``endpoint_name`` to a string literal rather than deriving its value is an intentional
decoupling of the API from the Models represented in it. When writing ViewSets, avoid the
tempation to do things like this::

    endpoint_name = Master._meta.verbose_name_plural
    endpoint_name = Detail.TYPE
    endpoint_name = anything_else_that_is_not_a_string_literal()

Serializers
^^^^^^^^^^^

Since Master ViewSets are never exposed in the API (they exist only to be subclassed by Detail
ViewSets), they don't need to have an attached Serializer. However, a Serializer *must* exist
representing the Master Model in a Master/Detail relationship, and every Serializer representing
Detail Models must subclass their respective Master Serializer.

Furthermore, every Serializer representing a Master Model should subclass a special Serializer
created for Master/Detail models, :class:`pulpcore.app.serializers.base.ModelSerializer`. This
Serializer includes a definition for the `type` field present on all models inheriting from
:class:`pulpcore.app.models.MasterModel`, and also identifies the `type` field as filterable,
centralizing common behavior that we're likely to want in all Serializers representing Models
in a Master/Detail Relationship.

Relating to Detail Serializers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When creating serializers for models that relate to Master/Detail models, a customized Serializer
field must be used that is Master/Detail aware so that URLs identifying the Detail Model instance
API representations are generated correctly.

In this case, instead of using a normal ``HyperlinkedRelatedField``,
:class:`pulpcore.app.serializers.base.DetailRelatedField` should be used. This field knows how to
correctly generate URLs to Detail types in the API by casting them down to their Detail Model
type, but should be used with care due to the inherent cost in calling ``cast()`` on an arbitrary
number of instances.

Identifying Detail Serializers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Similar to using ``DetailRelatedField``, Detail Model Serializers should use
:class:`pulpcore.app.serializers.base.DetailIdentityField` when declaring their ``pulp_href`` attribute,
so that the URLs generated by Detail Serializers return the proper URL to the cast Detail
object.


Pagination
----------

:term:`Pagination` support is provided by DRF, and should be used in the API to mitigate the
potentially negative effects caused by users attempting to iterate over large datasets. The
default pagination implementation use's DRF's ``CursorPagination`` method:

http://www.django-rest-framework.org/api-guide/pagination/#cursorpagination

Other methods are supported by DRF, and might be more appropriate in specific use-cases, but
cursor-based pagination provides the best support for our largest set of data, which is Content
stored in a Repository (or Repositories). By default, an object's id is used for the purposes
of cursor-based pagination, allowing an API user to reliably consume large datasets with no
duplicated entries.

Custom paginators can be easily created and attached to ViewSets using the ``paginator_class``
class attribute in the ViewSet class definition.


Filtering
---------

Filtering Backend
^^^^^^^^^^^^^^^^^

http://www.django-rest-framework.org/api-guide/filtering/#setting-filter-backends

We will be using the rest framework's DjangoFilterBackend. This is set as the default in the Django
settings.py, but can be overridden in individual ViewSets.

Allowing Filters
^^^^^^^^^^^^^^^^

Filters must be explicitly specified and are not enabled by default.


filterset_fields
****************

The simplest method of adding filters is simply to define `filterset_fields` on the ViewSet. Fields
specified here will be "filterable", but only using equality.

To use this request:

.. code-block:: bash

    http 'http://192.168.121.134:24817/pulp/api/v3/repositories/?name=singing-gerbil'

This is what the ViewSet should look like:

.. code-block:: python

    class RepositoryViewSet(viewsets.ModelViewSet):
        queryset = models.Repository.objects.all()
        serializer_class = serializers.RepositorySerializer
        filterset_fields = ('name',)


FilterSet
*********

Defining a `FilterSet` allows more options. To start with, this is a `ViewSet` and `FilterSet`
that allows the same request:

.. code-block:: bash

    http 'http://192.168.121.134:24817/pulp/api/v3/repositories/?name=singing-gerbil'


.. code:: python

    class RepositoryFilter(filters.FilterSet):
        pass

        class Meta:
            model = models.Repository
            fields = ['name']

    class RepositoryViewSet(viewsets.ModelViewSet):
        queryset = models.Repository.objects.all()
        serializer_class = serializers.RepositorySerializer
        filterset_class = RepositoryFilter


Beyond Equality
***************

A `FilterSet` also allows filters that are more advanced than equality. We have access to any of
the filters provided out of the box by `django-filter`.

https://django-filter.readthedocs.io/en/latest/ref/filters.html#filters

Simply define any filters in the `FilterSet` and then include them in `fields` in the Filter's Meta class.

`http 'http://192.168.121.134:24817/pulp/api/v3/repositories/?name_contains=singing'`

.. code-block:: python

    class RepositoryFilter(filters.FilterSet):
        name_contains = django_filters.filters.CharFilter(field_name='name', lookup_expr='contains')

        class Meta:
            model = models.Repository
            fields = ['name_contains']


Custom Filters
**************

If the filters provided by `django-filter` do not cover a use case, we can create custom filters
from the `django-filter` base classes.

"In" is a special relationship and is not covered by the base filters, however we can create a
custom filter based on the `BaseInFilter`.

.. code-block:: bash

    http 'http://192.168.121.134:24817/pulp/api/v3/repositories/?name_in_list=singing-gerbil,versatile-pudu'


.. code-block:: python

        class CharInFilter(django_filters.filters.BaseInFilter,
                           django_filters.filters.CharFilter):
            pass

        class RepositoryFilter(filters.FilterSet):
            name_in_list = CharInFilter(name='name', lookup_expr='in')

            class Meta:
                model = models.Repository
                fields = ['name_in_list']

.. note::

    We should be careful when naming these filters. Using `repo__in` would be fine because
    repo is not defined on this model. However, using `name__in` does *not* work because Django
    gets to it first looking for a subfield `in` on the name.


Documenting
-----------

By default, the docstring of a CRUD method on a ViewSet is used to generate that endpoint's
description. Individual parameters and responses are documented largely automatically based
on the Serializer field type, but using the "help_text" kwarg when defining serializer fields
lets us add a user-friendly string that is then included in the API endpoint.

ViewSets can override the ``get_view_description`` method to customize the source and formatting
of the description field, if desired. Serializer fields should set their ``help_text`` value for
every field defined to help API users know the purpose of each field represented in the API.

If a site-wide customization of docstring generation is desired, DRF provides a mechanism for
changing the default function used in ``get_view_description``:

http://www.django-rest-framework.org/api-guide/settings/#view_description_function

There are several support tools that work with DRF to aggregate endpoint documentation into
a browsable site of API docs, listed here:

http://www.django-rest-framework.org/topics/documenting-your-api/#endpoint-documentation

Because "DRF Docs" and "Django REST Swagger" do not generate documentation for responses,
Pulp is generating its REST API with `drf-spectacular <https://github.com/tfranzel/drf-spectacular>`_
until either DRF supports OpenAPI, or until CoreAPI supports response documentation.


Glossary
--------

.. glossary::

    DRF
        The Django Rest Framework.

    Pagination
        The practice of splitting large datasets into multiple pages.

    Router
        A :term:`DRF` API router exposes registered views (like a :term:`ViewSet`) at
        programatically-made URLs. Among other things, routers save us the trouble of having
        to manually write URLs for every API view.

        http://www.django-rest-framework.org/api-guide/routers/

    Serializer
        A :term:`DRF` Serializer is responsible for representing python objects in the API,
        and for converting API objects back into native python objects. Every model exposed
        via the API must have a related serializer.

        http://www.django-rest-framework.org/api-guide/serializers/

    ViewSet
        A :term:`DRF` ViewSet is a collection of views representing all API actions available
        at an API endpoint. ViewSets use a :term:`Serializer` or Serializers to correctly
        represent API-related objects, and are exposed in urls.py by being registered with
        a :term:`Router`. API actions provided by a ViewSet include "list", "create", "retreive",
        "update", "partial_update", and "destroy". Each action is one of the views that make up
        a ViewSet, and additional views can be added as-needed.

        http://www.django-rest-framework.org/api-guide/viewsets/
