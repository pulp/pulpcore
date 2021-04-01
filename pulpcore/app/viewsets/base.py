import warnings
from gettext import gettext as _
from urllib.parse import urlparse

from django.core.exceptions import FieldDoesNotExist, FieldError, ValidationError
from django.forms.utils import ErrorList
from django.urls import Resolver404, resolve
from django_filters.rest_framework import DjangoFilterBackend, filterset
from drf_spectacular.utils import extend_schema
from guardian.shortcuts import get_objects_for_user
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.generics import get_object_or_404
from pulpcore.openapi import PulpAutoSchema
from rest_framework.serializers import ValidationError as DRFValidationError

from pulpcore.app import tasks
from pulpcore.app.models import MasterModel
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer
from pulpcore.tasking.tasks import dispatch

# These should be used to prevent duplication and keep things consistent
NAME_FILTER_OPTIONS = ["exact", "in", "icontains", "contains", "startswith"]
# e.g.
# /?name=foo
# /?name__in=foo,bar
DATETIME_FILTER_OPTIONS = ["lt", "lte", "gt", "gte", "range"]
# e.g.
# /?pulp_created__gte=2018-04-12T19:45:52
# /?pulp_created__range=2018-04-12T19:45:52,2018-04-13T19:45:52


class DefaultSchema(PulpAutoSchema):
    """
    Overrides _allows_filters method to include filter fields only for read actions.

    Schema can be customised per view(set). Override this class and set it as a ``schema``
    attribute of a view(set) of interest.
    """

    def _allows_filters(self):
        """
        Include filter fields only for read actions, or GET requests.

        Returns:
            bool: True if filter fields should be included into the schema, False otherwise.
        """
        if getattr(self.view, "filter_backends", None) is None:
            return False

        if hasattr(self.view, "action"):
            return self.view.action in ["list"]

        return self.method.lower() in ["get"]


class StableOrderingFilter(OrderingFilter):
    """
    Ordering filter backend.

    Reference: https://github.com/encode/django-rest-framework/issues/6886#issuecomment-547120480
    """

    def get_ordering(self, request, queryset, view):
        """
        Ordering is set by a comma delimited ?ordering=... query parameter.

        The `ordering` query parameter can be overridden by setting the `ordering_param` value on
        the OrderingFilter or by specifying an `ORDERING_PARAM` value in the API settings.
        """
        ordering = super(StableOrderingFilter, self).get_ordering(request, queryset, view)
        try:
            field = queryset.model._meta.get_field("pulp_created")
        except FieldDoesNotExist:
            field = queryset.model._meta.pk

        if ordering is None:
            return ["-" + field.name]

        return list(ordering) + ["-" + field.name]


class NamedModelViewSet(viewsets.GenericViewSet):
    """
    A customized named ModelViewSet that knows how to register itself with the Pulp API router.

    This viewset is discoverable by its name.
    "Normal" Django Models and Master/Detail models are supported by the ``register_with`` method.

    Attributes:
        lookup_field (str): The name of the field by which an object should be looked up, in
            addition to any parent lookups if this ViewSet is nested. Defaults to 'pk'
        endpoint_name (str): The name of the final path segment that should identify the ViewSet's
            collection endpoint.
        nest_prefix (str): Optional prefix under which this ViewSet should be nested. This must
            correspond to the "parent_prefix" of a router with rest_framework_nested.NestedMixin.
            None indicates this ViewSet should not be nested.
        parent_lookup_kwargs (dict): Optional mapping of key names that would appear in self.kwargs
            to django model filter expressions that can be used with the corresponding value from
            self.kwargs, used only by a nested ViewSet to filter based on the parent object's
            identity.
        schema (DefaultSchema): The schema class to use by default in a viewset.
    """

    endpoint_name = None
    nest_prefix = None
    parent_viewset = None
    parent_lookup_kwargs = {}
    schema = DefaultSchema()
    filter_backends = (StableOrderingFilter, DjangoFilterBackend)

    def get_serializer_class(self):
        """
        Fetch the serializer class to use for the request.

        The default behavior is to use the "serializer_class" attribute on the viewset.
        We override that for the case where a "minimal_serializer_class" attribute is defined
        and where the request contains a query parameter of "minimal=True".

        The intention is that ViewSets can define a second, more minimal serializer with only
        the most important fields.
        """
        assert self.serializer_class is not None, _(
            "'{}' should either include a `serializer_class` attribute, or override the "
            "`get_serializer_class()` method.".format(self.__class__.__name__)
        )
        minimal_serializer_class = getattr(self, "minimal_serializer_class", None)

        if minimal_serializer_class:
            if getattr(self, "request", None):
                if "minimal" in self.request.query_params:
                    # the query param is a string, and non-empty strings evaluate True,
                    # so we need to do an actual string comparison to 'true'
                    if self.request.query_params["minimal"].lower() == "true":
                        return minimal_serializer_class

        return self.serializer_class

    @staticmethod
    def get_resource(uri, model):
        """
        Resolve a resource URI to an instance of the resource.

        Provides a means to resolve an href passed in a POST body to an
        instance of the resource.

        Args:
            uri (str): A resource URI.
            model (django.models.Model): A model class.

        Returns:
            django.models.Model: The resource fetched from the DB.

        Raises:
            rest_framework.exceptions.ValidationError: on invalid URI or resource not found.
        """
        try:
            match = resolve(urlparse(uri).path)
        except Resolver404:
            raise DRFValidationError(detail=_("URI not valid: {u}").format(u=uri))
        if "pk" in match.kwargs:
            kwargs = {"pk": match.kwargs["pk"]}
        else:
            kwargs = {}
            for key, value in match.kwargs.items():
                if key.endswith("_pk"):
                    kwargs["{}__pk".format(key[:-3])] = value
                else:
                    kwargs[key] = value
        try:
            return model.objects.get(**kwargs)
        except model.MultipleObjectsReturned:
            raise DRFValidationError(
                detail=_("URI {u} matches more than one {m}.").format(
                    u=uri, m=model._meta.model_name
                )
            )
        except model.DoesNotExist:
            raise DRFValidationError(
                detail=_("URI {u} not found for {m}.").format(u=uri, m=model._meta.model_name)
            )
        except ValidationError:
            raise DRFValidationError(detail=_("ID invalid: {u}").format(u=kwargs["pk"]))
        except FieldError:
            raise DRFValidationError(
                detail=_("URI {u} is not a valid {m}.").format(u=uri, m=model._meta.model_name)
            )

    @staticmethod
    def extract_pk(uri):
        """
        Resolve a resource URI to a simple PK value.

        Provides a means to resolve an href passed in a POST body to a primary key.
        Doesn't assume anything about whether the resource corresponding to the URI
        passed in actually exists.

        Note:
            Cannot be used with nested URIs where the PK of the final resource is not present.
            e.g. RepositoryVersion URI consists of repository PK and version number - no
            RepositoryVersion PK is present within the URI.

        Args:
            uri (str): A resource URI.

        Returns:
            primary_key (uuid.uuid4): The primary key of the resource extracted from the URI.

        Raises:
            rest_framework.exceptions.ValidationError: on invalid URI.
        """
        try:
            match = resolve(urlparse(uri).path)
        except Resolver404:
            raise DRFValidationError(detail=_("URI not valid: {u}").format(u=uri))

        try:
            return match.kwargs["pk"]
        except KeyError:
            raise DRFValidationError("URI does not contain an unqualified resource PK")

    @classmethod
    def is_master_viewset(cls):
        # ViewSet isn't related to a model, so it can't represent a master model
        if getattr(cls, "queryset", None) is None:
            return False

        # ViewSet is related to a MasterModel subclass that doesn't have its own related
        # master model, which makes this viewset a master viewset.
        if (
            issubclass(cls.queryset.model, MasterModel)
            and cls.queryset.model._meta.master_model is None
        ):
            return True

        return False

    @classmethod
    def view_name(cls):
        return "-".join(cls.endpoint_pieces())

    @classmethod
    def urlpattern(cls):
        return "/".join(cls.endpoint_pieces())

    @classmethod
    def endpoint_pieces(cls):
        # This is a core ViewSet, not Master/Detail. We can use the endpoint as is.
        if cls.queryset.model._meta.master_model is None:
            return [cls.endpoint_name]
        else:
            # Model is a Detail model. Go through its ancestry (via MRO) to find its
            # eldest superclass with a declared name, representing the Master ViewSet
            master_endpoint_name = None
            # first item in method resolution is the viewset we're starting with,
            # so start finding parents at the second item, index 1.
            for eldest in reversed(cls.mro()):
                try:
                    if eldest is not cls and eldest.endpoint_name is not None:
                        master_endpoint_name = eldest.endpoint_name
                        break
                except AttributeError:
                    # no endpoint_name defined, need to get more specific in the MRO
                    continue

            # if there is no master viewset or master endpoint name, just use endpoint_name
            if master_endpoint_name is None:
                return [cls.endpoint_name]

            # prepend endpoint of a plugin model with its Django app label
            app_label = cls.queryset.model._meta.app_label
            detail_endpoint_name = "{app_label}/{plugin_endpoint_name}".format(
                app_label=app_label, plugin_endpoint_name=cls.endpoint_name
            )

            pieces = [master_endpoint_name, detail_endpoint_name]

            # ensure that neither piece is None/empty and that they are not equal.
            if not all(pieces) or pieces[0] == pieces[1]:
                # unable to register; warn and return
                msg = (
                    "Unable to determine viewset inheritance path for master/detail "
                    "relationship represented by viewset {}. Does the Detail ViewSet "
                    "correctly subclass the Master ViewSet, and do both have endpoint_name "
                    "set to different values?"
                ).format(cls.__name__)
                warnings.warn(msg, RuntimeWarning)
                return []
            return pieces

    def initial(self, request, *args, **kwargs):
        """
        Runs anything that needs to occur prior to calling the method handler.

        For nested ViewSets, it checks that the parent object exists, otherwise return 404.
        For non-nested Viewsets, this does nothing.
        """
        if self.parent_lookup_kwargs:
            self.get_parent_field_and_object()
        super().initial(request, *args, **kwargs)

    def get_queryset(self):
        """
        Gets a QuerySet based on the current request.

        For nested ViewSets, this adds parent filters to the result returned by the superclass. For
        non-nested ViewSets, this returns the original QuerySet unchanged.

        Additional permissions-based filtering is provided for ViewSets that declare a
        ``queryset_filtering_required_permission`` attribute naming the permission users must have
        to view an object. This includes receiving the permission through either model-level,
        object-level, and access through either a user or group.

        Returns:
            django.db.models.query.QuerySet: The queryset returned by the superclass with additional
                filters applied that match self.parent_lookup_kwargs, to scope the results to only
                those associated with the parent object. Additionally the QuerySet is filtered by
                the permission named if the ViewSet declares a
                ``queryset_filtering_required_permission`` attribute.
        """
        qs = super().get_queryset()
        if self.parent_lookup_kwargs and self.kwargs:
            filters = {}
            for key, lookup in self.parent_lookup_kwargs.items():
                filters[lookup] = self.kwargs[key]
            qs = qs.filter(**filters)

        permission_name = getattr(self, "queryset_filtering_required_permission", None)
        if permission_name:
            qs = get_objects_for_user(self.request.user, permission_name, klass=qs)

        return qs

    @classmethod
    def _get_nest_depth(cls):
        """Return the depth that this ViewSet is nested."""
        if not cls.parent_lookup_kwargs:
            return 1
        return max([len(v.split("__")) for k, v in cls.parent_lookup_kwargs.items()])

    def get_parent_field_and_object(self):
        """
        For nested ViewSets, retrieve the nested parent implied by the url.

        Returns:
            tuple: (parent field name, parent)
        Raises:
            django.http.Http404: When the parent implied by the url does not exist. Synchronous
                                 use should allow this to bubble up and return a 404.
        """
        parent_field = None
        filters = {}
        if self.parent_lookup_kwargs:
            # Use the parent_lookup_kwargs and the url kwargs (self.kwargs) to retrieve the object
            for key, lookup in self.parent_lookup_kwargs.items():
                parent_field, _, parent_lookup = lookup.partition("__")
                filters[parent_lookup] = self.kwargs[key]
            return parent_field, get_object_or_404(self.parent_viewset.queryset, **filters)

    def get_parent_object(self):
        """
        For nested ViewSets, retrieve the nested parent implied by the url.

        Returns:
            pulpcore.app.models.Model: parent model object
        Raises:
            django.http.Http404: When the parent implied by the url does not exist. Synchronous
                                 use should allow this to bubble up and return a 404.
        """
        return self.get_parent_field_and_object()[1]


class AsyncReservedObjectMixin:
    """
    Mixin class providing the default method to compute the resources to reserve in the task.

    By default, lock the object instance we are working on.
    """

    def async_reserved_resources(self, instance):
        """
        Return the resources to reserve for the task created by the Async...Mixins.

        This default implementation locks the instance being worked on.

        .. note::

          This does not work for :class:`~pulpcore.app.viewsets.AsyncCreateMixin`
          (as there is no instance). Classes using :class:`~pulpcore.app.viewsets.AsyncCreateMixin`
          must override this method.

        Args:
            instance (django.models.Model): The instance that will be worked
                on by the task.

        Returns:
            list/str: The resources to put in the task's reservation

        Raises:
            AssertionError if instance is None (which happens for creation)

        """
        assert instance is not None, _(
            "'{}' must not use the default `async_reserved_resources` method "
            "when using create.".format(self.__class__.__name__)
        )
        return [instance]


class AsyncCreateMixin:
    """
    Provides a create method that dispatches a task with reservation.
    """

    @extend_schema(
        description="Trigger an asynchronous create task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request, *args, **kwargs):
        """
        Dispatches a task with reservation for creating an instance.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_label = self.queryset.model._meta.app_label
        task = dispatch(
            tasks.base.general_create,
            self.async_reserved_resources(None),
            args=(app_label, serializer.__class__.__name__),
            kwargs={"data": request.data},
        )
        return OperationPostponedResponse(task, request)


class AsyncUpdateMixin(AsyncReservedObjectMixin):
    """
    Provides an update method that dispatches a task with reservation
    """

    @extend_schema(
        description="Trigger an asynchronous update task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def update(self, request, pk, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        app_label = instance._meta.app_label
        task = dispatch(
            tasks.base.general_update,
            self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
            kwargs={"data": request.data, "partial": partial},
        )
        return OperationPostponedResponse(task, request)

    @extend_schema(
        description="Trigger an asynchronous partial update task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class AsyncRemoveMixin(AsyncReservedObjectMixin):
    """
    Provides a delete method that dispatches a task with reservation
    """

    @extend_schema(
        description="Trigger an asynchronous delete task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def destroy(self, request, pk, **kwargs):
        """
        Delete a model instance
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        app_label = instance._meta.app_label
        task = dispatch(
            tasks.base.general_delete,
            self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
        )
        return OperationPostponedResponse(task, request)


class BaseFilterSet(filterset.FilterSet):
    """
    Class to override django_filter's FilterSet and provide a way to set help text

    By default, this class will use predefined text and the field name to create help text for the
    filter. However, this can be overriden by setting a help_text dict with the the field name
    mapped to some help text:

        help_text = {'name__in': 'Lorem ipsum dolor', 'pulp_last_updated__lt': 'blah blah'}

    """

    help_text = {}

    # copied and modified from django_filter.conf
    LOOKUP_EXPR_TEXT = {
        "exact": _("matches"),
        "iexact": _("matches"),
        "contains": _("contains"),
        "icontains": _("contains"),
        "in": _("is in a comma-separated list of"),
        "gt": _("is greater than"),
        "gte": _("is greater than or equal to"),
        "lt": _("is less than"),
        "lte": _("is less than or equal to"),
        "startswith": _("starts with"),
        "istartswith": _("starts with"),
        "endswith": _("ends with"),
        "iendswith": _("ends with"),
        "range": _("is between two comma separated"),
        "isnull": _("has a null"),
        "regex": _("matches regex"),
        "iregex": _("matches regex"),
        "search": _("matches"),
        "ne": _("not equal to"),
    }

    @classmethod
    def filter_for_field(cls, field, name, lookup_expr):
        """
        Looks up and initializes a filter and returns it. Also, sets the help text on the filter.

        Args:
            field: The field class for the filter
            name: The name of filter field
            lookup_expr: The lookup expression that specifies how the field is matched
        Returns:
            django_filters.Filter: an initialized Filter object with help text
        """
        f = super().filter_for_field(field, name, lookup_expr)

        if cls.get_filter_name(name, lookup_expr) in cls.help_text:
            f.extra["help_text"] = cls.help_text[cls.get_filter_name(name, lookup_expr)]
        else:
            if lookup_expr in {"range", "in"}:
                val_word = _("values")
            else:
                val_word = _("value")

            f.extra["help_text"] = _("Filter results where {field} {expr} {value}").format(
                field=name, expr=cls.LOOKUP_EXPR_TEXT[lookup_expr], value=val_word
            )

        return f

    def is_valid(self, *args, **kwargs):
        is_valid = super().is_valid(*args, **kwargs)
        DEFAULT_FILTERS = [
            "exclude_fields",
            "fields",
            "limit",
            "minimal",
            "offset",
            "page_size",
            "ordering",
        ]
        for field in self.data.keys():
            if field in DEFAULT_FILTERS:
                continue

            if field not in self.filters:
                errors = self.form._errors.get("errors", ErrorList())
                errors.extend(["Invalid Filter: '{field}'".format(field=field)])
                self.form._errors["errors"] = errors
                is_valid = False

        return is_valid
