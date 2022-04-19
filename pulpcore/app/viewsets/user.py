from gettext import gettext as _

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework import mixins, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.app.models import Group
from pulpcore.app.models.role import GroupRole, Role, UserRole
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet, RolesMixin, NAME_FILTER_OPTIONS
from pulpcore.app.serializers import (
    GroupSerializer,
    GroupUserSerializer,
    GroupRoleSerializer,
    RoleSerializer,
    UserSerializer,
    UserRoleSerializer,
)

User = get_user_model()


class UserFilter(BaseFilterSet):
    """
    FilterSet for User.
    """

    class Meta:
        model = User
        fields = {
            "username": ["exact", "iexact", "in", "contains", "icontains"],
            "first_name": ["exact", "iexact", "in", "contains", "icontains"],
            "last_name": ["exact", "iexact", "in", "contains", "icontains"],
            "email": ["exact", "iexact", "in", "contains", "icontains"],
            "is_active": ["exact"],
            "is_staff": ["exact"],
        }


class UserViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for User.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "users"
    router_lookup = "user"
    filterset_class = UserFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    serializer_class = UserSerializer
    queryset = User.objects.all()
    ordering = ("-date_joined",)


class GroupFilter(BaseFilterSet):
    """
    FilterSet for Group.
    """

    class Meta:
        model = Group
        fields = {
            "id": ["exact", "in"],
            "name": ["exact", "iexact", "in", "contains", "icontains"],
        }


class GroupViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    RolesMixin,
):
    """
    ViewSet for Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "groups"
    router_lookup = "group"
    filterset_class = GroupFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    serializer_class = GroupSerializer
    queryset = Group.objects.all()
    ordering = ("name",)
    queryset_filtering_required_permission = "core.view_group"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_perms:core.add_group",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_group",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.change_group",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.delete_group",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_obj_perms:core.manage_roles_group"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.group_owner"},
            },
        ],
    }

    LOCKED_ROLES = {
        "core.group_creator": [
            "core.add_group",
        ],
        "core.group_owner": [
            "core.view_group",
            "core.change_group",
            "core.delete_group",
            "core.manage_roles_group",
        ],
        "core.group_viewer": [
            "core.view_group",
        ],
    }


class GroupUserViewSet(NamedModelViewSet):
    """
    ViewSet for Users that belong to a Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "users"
    router_lookup = "user"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "groups__pk"}
    serializer_class = GroupUserSerializer
    queryset = User.objects.all()

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_group_model_or_obj_perms:core.view_group",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_group_model_or_obj_perms:core.change_group",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_group_model_or_obj_perms:core.change_group",
            },
        ],
        "creation_hooks": [],
    }

    def list(self, request, group_pk):
        """
        List group users.
        """
        group = Group.objects.get(pk=group_pk)
        queryset = group.user_set.all()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = GroupUserSerializer(page, context={"request": request}, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, group_pk):
        """
        Add a user to a group.
        """
        group = Group.objects.get(pk=group_pk)
        if not request.data:
            raise ValidationError(
                _("Please provide one of the following values for User: 'pk', 'id', 'username'")
            )
        try:
            user = User.objects.get(**request.data)
        except (User.DoesNotExist, FieldError) as exc:
            raise ValidationError(str(exc))
        group.user_set.add(user)
        group.save()
        serializer = GroupUserSerializer(user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, group_pk, pk):
        """
        Remove a user from a group.
        """
        group = Group.objects.get(pk=group_pk)
        user = get_object_or_404(User, pk=pk)
        group.user_set.remove(user)
        group.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleFilter(BaseFilterSet):
    """
    FilterSet for Role.
    """

    class Meta:
        model = Role
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "description": ["exact", "iexact", "icontains", "contains"],
            "locked": ["exact"],
        }


class RoleViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for Role.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "roles"
    router_lookup = "role"
    filterset_class = RoleFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    serializer_class = RoleSerializer
    queryset = Role.objects.all()
    ordering = ("name",)

    def get_object(self, **kwargs):
        instance = super().get_object(**kwargs)
        if instance.locked and self.request.method not in SAFE_METHODS:
            raise PermissionDenied(detail=_("The role is locked."))
        return instance


class _CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


class NestedRoleFilter(BaseFilterSet):
    """
    FilterSet for Roles nested under users / groups.
    """

    # For some reason the generated Filters don't work here
    role = filters.CharFilter(field_name="role__name")
    role__in = _CharInFilter(field_name="role__name", lookup_expr="in")
    role__contains = filters.CharFilter(field_name="role__name", lookup_expr="contains")
    role__icontains = filters.CharFilter(field_name="role__name", lookup_expr="icontains")
    role__startswith = filters.CharFilter(field_name="role__name", lookup_expr="startswith")
    content_object = filters.CharFilter(
        label="content_object", method="content_object_filter_function"
    )

    def content_object_filter_function(self, queryset, name, value):
        if value == "null":
            return queryset.filter(object_id=None)
        else:
            try:
                obj = NamedModelViewSet.get_resource(value)
            except ValidationError:
                raise ValidationError(_("Invalid value for 'content_object': {}.").format(value))
            obj_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
            return queryset.filter(content_type_id=obj_type.id, object_id=obj.pk)

    class Meta:
        fields = (
            "role",
            "role__in",
            "role__contains",
            "role__icontains",
            "role__startswith",
            "content_object",
        )


class UserRoleFilter(NestedRoleFilter):
    """
    FilterSet for UserRole.
    """

    class Meta:
        model = UserRole
        fields = NestedRoleFilter.Meta.fields


class UserRoleViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for UserRole.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "roles"
    router_lookup = "user"
    parent_viewset = UserViewSet
    parent_lookup_kwargs = {"user_pk": "user__pk"}
    filterset_class = UserRoleFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    serializer_class = UserRoleSerializer
    queryset = UserRole.objects.all()
    ordering = ("-pulp_created",)


class GroupRoleFilter(NestedRoleFilter):
    """
    FilterSet for GroupRole.
    """

    class Meta:
        model = GroupRole
        fields = NestedRoleFilter.Meta.fields


class GroupRoleViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for GroupRole.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "roles"
    router_lookup = "group"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "group__pk"}
    filterset_class = GroupRoleFilter
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    serializer_class = GroupRoleSerializer
    queryset = GroupRole.objects.all()
    ordering = ("-pulp_created",)
