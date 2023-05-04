import warnings
from gettext import gettext as _
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.core.exceptions import FieldError, ValidationError
from django.urls import Resolver404, resolve
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from pulpcore.openapi import PulpAutoSchema
from rest_framework.serializers import ValidationError as DRFValidationError, ListField, CharField

from pulpcore.app import tasks
from pulpcore.app.models import MasterModel
from pulpcore.app.models.role import GroupRole, UserRole
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.role_util import get_objects_for_user
from pulpcore.app.serializers import AsyncOperationResponseSerializer, NestedRoleSerializer
from pulpcore.app.util import get_viewset_for_model
from pulpcore.tasking.tasks import dispatch

# These should be used to prevent duplication and keep things consistent
NAME_FILTER_OPTIONS = ["exact", "in", "icontains", "contains", "startswith"]
# e.g.
# /?name=foo
# /?name__in=foo,bar
DATETIME_FILTER_OPTIONS = ["exact", "lt", "lte", "gt", "gte", "range"]
# e.g.
# /?pulp_created__gte=2018-04-12T19:45:52
# /?pulp_created__range=2018-04-12T19:45:52,2018-04-13T19:45:52
NULLABLE_NUMERIC_FILTER_OPTIONS = ["exact", "ne", "lt", "lte", "gt", "gte", "range", "isnull"]


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

    def get_serializer_class(self):
        """
        Fetch the serializer class to use for the request.

        The default behavior is to use the "serializer_class" attribute on the viewset.
        We override that for the case where a "minimal_serializer_class" attribute is defined
        and where the request contains a query parameter of "minimal=True".

        The intention is that ViewSets can define a second, more minimal serializer with only
        the most important fields.
        """
        assert self.serializer_class is not None, (
            "'{}' should either include a `serializer_class` attribute, or override the "
            "`get_serializer_class()` method."
        ).format(self.__class__.__name__)
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
    def get_resource_model(uri):
        """
        Resolve a resource URI to the model for the resource.

        Provides a means to resolve an href passed in a POST body to an
        model for the resource.

        Args:
            uri (str): A resource URI.

        Returns:
            django.models.Model: The model for the specified URI.

        Raises:
            rest_framework.exceptions.ValidationError: on invalid URI.
        """
        try:
            match = resolve(urlparse(uri).path)
        except Resolver404:
            raise DRFValidationError(detail=_("URI not valid: {u}").format(u=uri))

        return match.func.cls.queryset.model

    @staticmethod
    def get_resource(uri, model=None):
        """
        Resolve a resource URI to an instance of the resource.

        Provides a means to resolve an href passed in a POST body to an
        instance of the resource.

        Args:
            uri (str): A resource URI.
            model (django.models.Model): A model class. If not provided, the method automatically
                determines the used model from the resource URI.

        Returns:
            django.models.Model: The resource fetched from the DB.

        Raises:
            rest_framework.exceptions.ValidationError: on invalid URI or resource not found.
        """
        try:
            match = resolve(urlparse(uri).path)
        except Resolver404:
            raise DRFValidationError(detail=_("URI not valid: {u}").format(u=uri))

        if model is None:
            model = match.func.cls.queryset.model

        if "pk" in match.kwargs:
            kwargs = {"pk": match.kwargs["pk"]}
        else:
            kwargs = {}
            for key, value in match.kwargs.items():
                if key.endswith("_pk"):
                    kwargs["{}__pk".format(key[:-3])] = value
                elif key == "pulp_domain":
                    if hasattr(model, "pulp_domain"):
                        kwargs["pulp_domain__name"] = value
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
    def routable(cls) -> bool:
        # Determines if ViewSet should be added to router
        return not cls.is_master_viewset()

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

        Additional permissions-based filtering can be performed if enabled by the permission class
        and ViewSet. The default permission class AccessPolicyFromDB will see if a queryset_scoping
        method is defined and call that method to further scope the queryset on user permissions.

        Returns:
            django.db.models.query.QuerySet: The queryset returned by the superclass with additional
                filters applied that match self.parent_lookup_kwargs, to scope the results to only
                those associated with the parent object. Additional queryset filtering could be
                performed if queryset_scoping is enabled.
        """
        qs = super().get_queryset()

        if self.parent_lookup_kwargs and self.kwargs:
            filters = {}
            for key, lookup in self.parent_lookup_kwargs.items():
                filters[lookup] = self.kwargs[key]
            qs = qs.filter(**filters)

        if request := getattr(self, "request", None):
            if settings.DOMAIN_ENABLED:
                if hasattr(qs.model, "pulp_domain"):
                    qs = qs.filter(pulp_domain=request.pulp_domain)

            for permission_class in self.get_permissions():
                if hasattr(permission_class, "scope_queryset"):
                    qs = permission_class.scope_queryset(self, qs)

        return qs

    def scope_queryset(self, qs):
        """
        A default queryset scoping method implementation for all NamedModelViewSets.

        If the ViewSet is not a Master ViewSet, then it'll perform scoping based on the ViewSet's
        `queryset_filtering_required_permission` attribute if present.
        Else it will call each child's view `get_queryset()` method to determine what objects the
        user can see.

        This method is intended to be overriden by subclasses if different behavior is desired.
        """
        if not self.request.user.is_superuser:
            if not self.is_master_viewset():
                # subclass so use default scope_queryset implementation
                permission_name = getattr(self, "queryset_filtering_required_permission", None)
                if permission_name:
                    user = self.request.user
                    qs = get_objects_for_user(user, permission_name, qs)
            else:
                # master view so loop through each subclass to find scoped objects
                pks = []
                for model in self.queryset.model.__subclasses__():
                    if viewset_model := get_viewset_for_model(model, ignore_error=True):
                        viewset = viewset_model()
                        setattr(viewset, "request", self.request)
                        pks.extend(viewset.get_queryset().values_list("pk", flat=True))
                qs = qs.filter(pk__in=pks)
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
        assert instance is not None, (
            "'{}' must not use the default `async_reserved_resources` method " "when using create."
        ).format(self.__class__.__name__)
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
            exclusive_resources=self.async_reserved_resources(None),
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
            exclusive_resources=self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
            kwargs={"data": request.data, "partial": partial},
            immediate=True,
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
            exclusive_resources=self.async_reserved_resources(instance),
            args=(pk, app_label, serializer.__class__.__name__),
            immediate=True,
        )
        return OperationPostponedResponse(task, request)


class RolesMixin:
    @extend_schema(
        description="List roles assigned to this object.",
        responses={
            200: inline_serializer(
                name="ObjectRolesSerializer",
                fields={"roles": ListField(child=NestedRoleSerializer())},
            )
        },
    )
    @action(detail=True, methods=["get"])
    def list_roles(self, request, pk):
        obj = self.get_object()
        obj_type = ContentType.objects.get_for_model(obj)
        user_qs = UserRole.objects.filter(
            content_type_id=obj_type.id, object_id=obj.pk
        ).select_related("user", "role")
        group_qs = GroupRole.objects.filter(
            content_type_id=obj_type.id, object_id=obj.pk
        ).select_related("group", "role")
        roles = {}
        for user_role in user_qs:
            if user_role.role.name not in roles:
                roles[user_role.role.name] = {
                    "role": user_role.role.name,
                    "users": [],
                    "groups": [],
                }
            roles[user_role.role.name]["users"].append(user_role.user.username)
        for group_role in group_qs:
            if group_role.role.name not in roles:
                roles[group_role.role.name] = {
                    "role": group_role.role.name,
                    "users": [],
                    "groups": [],
                }
            roles[group_role.role.name]["groups"].append(group_role.group.name)
        result = {"roles": list(roles.values())}
        return Response(result)

    @extend_schema(
        description="Add a role for this object to users/groups.",
        responses={201: NestedRoleSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=NestedRoleSerializer)
    def add_role(self, request, pk):
        obj = self.get_object()
        serializer = NestedRoleSerializer(
            data=request.data, context={"request": request, "content_object": obj, "assign": True}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if serializer.validated_data["users"]:
                UserRole.objects.bulk_create(
                    [
                        UserRole(
                            content_object=obj,
                            user=user,
                            role=serializer.validated_data["role"],
                        )
                        for user in serializer.validated_data["users"]
                    ]
                )
            if serializer.validated_data["groups"]:
                GroupRole.objects.bulk_create(
                    [
                        GroupRole(
                            content_object=obj,
                            group=group,
                            role=serializer.validated_data["role"],
                        )
                        for group in serializer.validated_data["groups"]
                    ]
                )
        return Response(serializer.data, status=201)

    @extend_schema(
        description="Remove a role for this object from users/groups.",
        responses={201: NestedRoleSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=NestedRoleSerializer)
    def remove_role(self, request, pk):
        obj = self.get_object()
        serializer = NestedRoleSerializer(
            data=request.data, context={"request": request, "content_object": obj, "assign": False}
        )
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            UserRole.objects.filter(pk__in=serializer.user_role_pks).delete()
            GroupRole.objects.filter(pk__in=serializer.group_role_pks).delete()
        return Response(serializer.data, status=201)

    @extend_schema(
        description="List permissions available to the current user on this object.",
        responses={
            200: inline_serializer(
                name="MyPermissionsSerializer", fields={"permissions": ListField(child=CharField())}
            )
        },
    )
    @action(detail=True, methods=["get"])
    def my_permissions(self, request, pk=None):
        obj = self.get_object()
        app_label = obj._meta.app_label
        permissions = [
            ".".join((app_label, codename)) for codename in request.user.get_all_permissions(obj)
        ]
        return Response({"permissions": permissions})
