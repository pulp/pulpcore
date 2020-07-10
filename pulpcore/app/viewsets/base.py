import re
import warnings
from gettext import gettext as _
from urllib.parse import urlparse

from django.core.exceptions import FieldDoesNotExist, FieldError, ValidationError
from django.forms.utils import ErrorList
from django.urls import Resolver404, resolve
from django_filters.rest_framework import DjangoFilterBackend, filterset
from drf_yasg.utils import swagger_auto_schema, get_serializer_ref_name
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.generics import get_object_or_404
from rest_framework.schemas.openapi import AutoSchema, SchemaGenerator
from rest_framework.schemas.utils import is_list_view
from rest_framework import serializers
from rest_framework.serializers import ValidationError as DRFValidationError

from pulpcore.app import tasks
from pulpcore.app.models import MasterModel
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer
from pulpcore.tasking.tasks import enqueue_with_reservation

# These should be used to prevent duplication and keep things consistent
NAME_FILTER_OPTIONS = ["exact", "in"]
# e.g.
# /?name=foo
# /?name__in=foo,bar
DATETIME_FILTER_OPTIONS = ["lt", "lte", "gt", "gte", "range"]
# e.g.
# /?pulp_created__gte=2018-04-12T19:45:52
# /?pulp_created__range=2018-04-12T19:45:52,2018-04-13T19:45:52


class PulpSchemaGenerator(SchemaGenerator):
    def get_schema(self, request=None, public=False):
        """
        Generate a OpenAPI schema.
        """
        self._initialise_endpoints()

        paths, components = self.get_paths(request, public)
        if not paths:
            return None

        schema = {
            "openapi": "3.0.2",
            "info": self.get_info(),
            "servers": [{"url": "http://localhost:24817/"}],
            "security": [{"basicAuth": []}],
            "components": components,
            "paths": paths,
        }

        return schema

    @staticmethod
    def get_parameter_slug_from_model(model, prefix):
        """Returns a path parameter name for the resource associated with the model.

        Args:
            model (django.db.models.Model): The model for which a path parameter name is needed
            prefix (str): Optional prefix to add to the slug

        Returns:
            str: *pulp_href where * is the model name in all lower case letters
        """
        slug = "%s_href" % "_".join(
            [part.lower() for part in re.findall("[A-Z][^A-Z]*", model.__name__)]
        )
        if prefix:
            return "{}_{}".format(prefix, slug)
        else:
            return slug

    def convert_endpoint_path_params(self, path, view):
        """Replaces all 'pulp_id' path parameters with a specific name for the primary key.

        This method is used to ensure that the primary key name is consistent between nested
        endpoints. get_endpoints() returns paths that use 'pulp_id' for the top level path and a
        specific name for the nested paths. e.g.: repository_pk.

        This ensures that when the endpoints are sorted, the parent endpoint appears before the
        endpoints nested under it.

        Args:
            endpoints (dict): endpoints as returned by get_endpoints

        Returns:
            dict: The enpoints dictionary with modified primary key path parameter names.
        """
        from pulpcore.app.models import RepositoryVersion

        if not hasattr(view, "queryset") or view.queryset is None:
            if hasattr(view, "model"):
                resource_model = view.model
            else:
                return path
        else:
            resource_model = view.queryset.model
        if resource_model:
            prefix_ = None
            if issubclass(resource_model, RepositoryVersion):
                prefix_ = view.parent_viewset.endpoint_name
            param_name = self.get_parameter_slug_from_model(resource_model, prefix_)
            resource_path = "%s}/" % path.rsplit(sep="}", maxsplit=1)[0]
            path = path.replace(resource_path, "{%s}" % param_name)
        return path

    def get_paths(self, request=None, public=False):
        from urllib.parse import urljoin
        import uritemplate

        result = {}
        components = {
            "securitySchemes": {"basicAuth": {"type": "http", "scheme": "basic"}},
            "schemas": {},
        }

        plugins = None
        if "bindings" in request.query_params:
            plugins = [request.query_params["plugin"]]

        paths, view_endpoints = self._get_paths_and_endpoints(None if public else request)

        # Only generate the path prefix for paths that will be included
        if not paths:
            return None

        for path, method, view in view_endpoints:
            plugin = view.__module__.split(".")[0]
            if plugins and plugin not in plugins:
                continue
            if not self.has_view_permissions(path, method, view):
                continue
            variables = uritemplate.variables(path)
            view_name = view.view_name() if "view_name" in dir(view) else path
            old_path = path
            if len(variables) == 1:
                path = self.convert_endpoint_path_params(path, view)
            subpath = re.findall(r"[a-zA-Z]+", view_name)
            if len(subpath) == 1 and old_path != path:
                subpath = old_path.replace("/pulp/api/v3", "").strip("/").split("/")

            title_path = []
            for string in subpath:
                if f"{string}s" in subpath:
                    continue
                if "{" not in string and string.title() not in title_path:
                    title_path.append(string.title())
            operation = view.schema.get_operation(path, method)
            operation["tags"] = ["".join(title_path)]
            if "component" in operation["responses"]:
                for ref_name, response_schema in operation["responses"]["component"].items():
                    components["schemas"][ref_name] = response_schema
                del operation["responses"]["component"]
            if "component" in operation.get("requestBody", {}):
                for ref_name, content_schema in operation["requestBody"]["component"].items():
                    components["schemas"][ref_name] = content_schema
                del operation["requestBody"]["component"]

            # Normalise path for any provided mount url.
            if path.startswith("/"):
                path = path[1:]
            if not path.startswith("{"):
                path = urljoin(self.url or "/", path)

            result.setdefault(path, {})
            result[path][method.lower()] = operation

        return result, components


class DefaultSchema(AutoSchema):
    """
    Overrides _allows_filters method to include filter fields only for read actions.

    Schema can be customised per view(set). Override this class and set it as a ``schema``
    attribute of a view(set) of interest.
    """

    def _allows_filters(self, path, method):
        """
        Include filter fields only for read actions, or GET requests.

        Args:
            path: Route path for view from URLConf.
            method: The HTTP request method.
        Returns:
            bool: True if filter fields should be included into the schema, False otherwise.
        """
        if getattr(self.view, "filter_backends", None) is None:
            return False

        if hasattr(self.view, "action"):
            return self.view.action in ["list"]

        return method.lower() in ["get"]

    def _get_responses(self, path, method):
        # TODO: Handle multiple codes and pagination classes.
        if method == "DELETE":
            return {"204": {"description": ""}}

        item_schema = {}
        serializer = self._get_serializer(path, method)
        ref_name = get_serializer_ref_name(serializer)
        ref_name = "".join(ref_name.split("."))

        # Getting serializer from @swagger_auto_schema
        action = getattr(self.view, "action", method.lower())
        action_method = getattr(self.view, action, None)
        overrides = getattr(action_method, "_swagger_auto_schema", {})
        responses = overrides.get(method.lower(), overrides).get("responses")
        if responses:
            for key, value in responses.items():
                serializer = value()
            ref_name = serializer.__class__.__name__.replace("Serializer", "")

        reference = {"$ref": f"#/components/schemas/{ref_name}"}

        if isinstance(serializer, serializers.Serializer):
            item_schema = self._map_serializer(serializer)
            # No write_only fields for response.
            for name, schema in item_schema["properties"].copy().items():
                if "writeOnly" in schema:
                    del item_schema["properties"][name]
                    if "required" in item_schema:
                        item_schema["required"] = [f for f in item_schema["required"] if f != name]

        if is_list_view(path, method, self.view):
            response_schema = {
                "type": "array",
                "items": reference,
            }
            paginator = self._get_pagninator()
            if paginator:
                response_schema = paginator.get_paginated_response_schema(response_schema)
        else:
            response_schema = reference

        item_schema["type"] = "object"

        return {
            "component": {ref_name: item_schema},
            "200": {
                "content": {ct: {"schema": response_schema} for ct in self.content_types},
                # description is a mandatory property,
                # https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.0.2.md#responseObject
                # TODO: put something meaningful into it
                "description": "",
            },
        }

    def _get_request_body(self, path, method):
        if method not in ("PUT", "PATCH", "POST"):
            return {}

        serializer = self._get_serializer(path, method)

        if not isinstance(serializer, serializers.Serializer):
            return {}

        ref_name = get_serializer_ref_name(serializer)
        ref_name = "".join(ref_name.split("."))
        # ref_name = f"Pulp{ref_name}"

        reference = {"$ref": f"#/components/schemas/{ref_name}"}

        content = self._map_serializer(serializer)
        # No required fields for PATCH
        if method == "PATCH":
            del content["required"]
        # No read_only fields for request.
        # for name, schema in content['properties'].copy().items():
        #     if 'readOnly' in schema:
        #         del content['properties'][name]

        content["type"] = "object"

        return {
            "component": {ref_name: content},
            "required": True,
            "content": {ct: {"schema": reference} for ct in self.content_types},
        }

    def _get_operation_id(self, path, method):
        """
        Compute an operation ID from the model, serializer or view name.
        """
        method_name = getattr(self.view, "action", method.lower())
        if is_list_view(path, method, self.view):
            action = "list"
        elif method_name not in self.method_mapping:
            action = method_name
        else:
            action = self.method_mapping[method.lower()]
        return action.replace("destroy", "delete").replace("retrieve", "read")


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

        Returns:
            django.db.models.query.QuerySet: The queryset returned by the superclass with additional
                filters applied that match self.parent_lookup_kwargs, to scope the results to only
                those associated with the parent object.
        """
        qs = super().get_queryset()
        if self.parent_lookup_kwargs and self.kwargs:
            filters = {}
            for key, lookup in self.parent_lookup_kwargs.items():
                filters[lookup] = self.kwargs[key]
            qs = qs.filter(**filters)
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

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous create task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request, *args, **kwargs):
        """
        Dispatches a task with reservation for creating an instance.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app_label = self.queryset.model._meta.app_label
        async_result = enqueue_with_reservation(
            tasks.base.general_create,
            self.async_reserved_resources(None),
            args=(app_label, serializer.__class__.__name__),
            kwargs={"data": request.data},
        )
        return OperationPostponedResponse(async_result, request)


class AsyncUpdateMixin(AsyncReservedObjectMixin):
    """
    Provides an update method that dispatches a task with reservation
    """

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous update task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def update(self, request, pk, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        app_label = instance._meta.app_label
        async_result = enqueue_with_reservation(
            tasks.base.general_update,
            self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
            kwargs={"data": request.data, "partial": partial},
        )
        return OperationPostponedResponse(async_result, request)

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous partial update task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class AsyncRemoveMixin(AsyncReservedObjectMixin):
    """
    Provides a delete method that dispatches a task with reservation
    """

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous delete task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def destroy(self, request, pk, **kwargs):
        """
        Delete a model instance
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        app_label = instance._meta.app_label
        async_result = enqueue_with_reservation(
            tasks.base.general_delete,
            self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
        )
        return OperationPostponedResponse(async_result, request)


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
