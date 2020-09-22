from gettext import gettext as _
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import FieldError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from guardian.models.models import GroupObjectPermission
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.app.viewsets.base import NamedModelViewSet
from pulpcore.app.serializers.user import (
    GroupSerializer,
    GroupUserSerializer,
    PermissionSerializer,
    UserSerializer,
)

User = get_user_model()


class UserViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    """
    ViewSet for User.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "users"
    serializer_class = UserSerializer
    queryset = User.objects.all()

    @extend_schema(description="List user permissions.")
    @action(detail=True, methods=["get"], serializer_class=PermissionSerializer)
    def permissions(self, request, pk):
        """
        List user permissions.
        """
        user = self.get_object()
        object_permission = PermissionSerializer(user.userobjectpermission_set.all(), many=True)
        permissions = PermissionSerializer(user.user_permissions.all(), many=True)
        return Response(object_permission.data + permissions.data)


class GroupViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    """
    ViewSet for Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "groups"
    router_lookup = "group"
    serializer_class = GroupSerializer
    queryset = Group.objects.all()


class GroupModelPermissionViewSet(NamedModelViewSet):
    """
    ViewSet for Model Permissions that belongs to a Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "model_permissions"
    nest_prefix = "groups"
    router_lookup = "model_permission"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "group__pk"}
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()

    def get_model_permission(self, request):
        """Get model permission"""
        data = {}
        for key, value in request.data.items():
            if key == "permission":
                if "." in value:
                    data["content_type__app_label"], data["codename"] = value.split(".", maxsplit=1)
                else:
                    data["codename"] = value
                continue

            if key == "pulp_href":
                if "id" in data.keys():
                    continue
                data["id"] = value.strip("/").split("/")[-1]
                continue

            data[key] = value

        try:
            permission = Permission.objects.get(**data)
        except (Permission.MultipleObjectsReturned, Permission.DoesNotExist, FieldError) as exc:
            raise ValidationError(str(exc))

        return permission

    @extend_schema(description="Retrieve a model permission from a group.")
    def retrieve(self, request, group_pk, pk):
        instance = get_object_or_404(Permission, pk=pk)
        serializer = PermissionSerializer(instance, context={"group_pk": group_pk})
        return Response(serializer.data)

    @extend_schema(description="List group permissions.", responses={200: PermissionSerializer})
    def list(self, request, group_pk):
        """
        List group model permissions.
        """
        group = Group.objects.get(pk=group_pk)
        queryset = group.permissions.all()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PermissionSerializer(page, context={"group_pk": group_pk}, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PermissionSerializer(queryset, context={"group_pk": group_pk}, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Add a model permission to a group.", responses={201: PermissionSerializer}
    )
    def create(self, request, group_pk):
        """
        Add a model permission to a group.
        """
        group = Group.objects.get(pk=group_pk)
        permission = self.get_model_permission(request)
        group.permissions.add(permission)
        group.save()
        serializer = PermissionSerializer(permission, context={"group_pk": group_pk})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(description="Remove a model permission from a group.")
    def destroy(self, request, group_pk, pk):
        """
        Remove a model permission from a group.
        """
        group = Group.objects.get(pk=group_pk)
        permission = get_object_or_404(Permission, pk=pk)
        group.permissions.remove(permission)
        group.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupObjectPermissionViewSet(NamedModelViewSet):
    """
    ViewSet for Object Permissions that belongs to a Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "object_permissions"
    nest_prefix = "groups"
    router_lookup = "object_permission"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "group__pk"}
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()

    def get_object_pk(self, request):
        """Get object pk."""

        if "obj" not in request.data:
            raise ValidationError(_("Please provide 'obj' value"))
        try:
            obj_pk = request.data["obj"].strip("/").split("/")[-1]
            uuid.UUID(obj_pk)
        except (AttributeError, ValueError):
            raise ValidationError(_("Invalid value for 'obj': {obj}").format(request.data["obj"]))

        return obj_pk

    def get_model_permission(self, request):
        """Get model permission"""

        if "permission" not in request.data:
            raise ValidationError(_("Please provide 'permission' value"))

        codename = request.data["permission"].split(".")[-1]

        try:
            permission = Permission.objects.get(codename=codename)
        except (Permission.MultipleObjectsReturned, Permission.DoesNotExist, FieldError) as exc:
            raise ValidationError(str(exc))

        return permission

    @extend_schema(description="Retrieve a model permission from a group.")
    def retrieve(self, request, group_pk, pk):
        instance = get_object_or_404(GroupObjectPermission, pk=pk)
        serializer = PermissionSerializer(instance, context={"group_pk": group_pk})
        return Response(serializer.data)

    @extend_schema(
        description="List group object permissions.", responses={200: PermissionSerializer}
    )
    def list(self, request, group_pk):
        """
        List group object permissions.
        """
        group = Group.objects.get(pk=group_pk)
        queryset = group.groupobjectpermission_set.all()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = PermissionSerializer(page, context={"group_pk": group_pk}, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = PermissionSerializer(queryset, context={"group_pk": group_pk}, many=True)
        return Response(serializer.data)

    @extend_schema(
        description="Add an object permission to a group.", responses={201: PermissionSerializer}
    )
    def create(self, request, group_pk):
        """
        Create an object permission to a group.
        """
        group = Group.objects.get(pk=group_pk)
        permission = self.get_model_permission(request)
        object_pk = self.get_object_pk(request)
        object_permission = GroupObjectPermission(
            group=group,
            permission=permission,
            content_type_id=permission.content_type_id,
            object_pk=object_pk,
        )
        object_permission.save()
        serializer = PermissionSerializer(object_permission, context={"group_pk": group_pk})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(description="Remove an object permission from a group.")
    def destroy(self, request, group_pk, pk):
        """
        Delete an object permission from a group.
        """
        object_permission = get_object_or_404(GroupObjectPermission, pk=pk, group_id=group_pk)
        object_permission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GroupUserViewSet(NamedModelViewSet):
    """
    ViewSet for Users that belongs to a Group.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "users"
    nest_prefix = "groups"
    router_lookup = "user"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "groups__pk"}
    serializer_class = GroupUserSerializer
    queryset = User.objects.all()

    def list(self, request, group_pk):
        """
        List group users.
        """
        group = Group.objects.get(pk=group_pk)
        queryset = group.user_set.all()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = GroupUserSerializer(page, context={"request": None}, many=True)
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
        serializer = GroupUserSerializer(user, context={"request": None})
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
