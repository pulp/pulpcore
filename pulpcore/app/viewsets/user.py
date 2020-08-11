from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.app.viewsets.base import NamedModelViewSet
from pulpcore.app.serializers.user import (
    GroupSerializer,
    GroupUserSerializer,
    ObjectPermissionSerializer,
    PermissionSerializer,
    UserSerializer,
)


class UserViewSet(
    NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin,
):
    """
    ViewSet for User.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "users"
    serializer_class = UserSerializer
    queryset = get_user_model().objects.all()

    @extend_schema(description="List user permissions.",)
    @action(detail=True, methods=["get"], serializer_class=ObjectPermissionSerializer)
    def permissions(self, request, pk):
        """
        List user permissions.
        """
        user = self.get_object()
        object_permission = ObjectPermissionSerializer(
            user.userobjectpermission_set.all(), many=True
        )
        permissions = ObjectPermissionSerializer(user.user_permissions.all(), many=True)
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

    @extend_schema(description="List group users.",)
    @action(detail=True, methods=["get"], serializer_class=GroupUserSerializer)
    def users(self, request, pk):
        """
        List group users.
        """
        group = self.get_object()
        serializer = GroupUserSerializer(group.user_set.all(), many=True)
        return Response(serializer.data)


class PermissionViewSet(NamedModelViewSet):
    """
    ViewSet for Permission.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    endpoint_name = "permissions"
    nest_prefix = "groups"
    router_lookup = "permission"
    parent_viewset = GroupViewSet
    parent_lookup_kwargs = {"group_pk": "group__pk"}
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()

    @extend_schema(
        description="List group permissions.", responses={200: ObjectPermissionSerializer}
    )
    def list(self, request, group_pk):
        """
        List group permissions.
        """
        group = Group.objects.get(pk=group_pk)
        object_permission = ObjectPermissionSerializer(
            group.groupobjectpermission_set.all(), many=True
        )
        permissions = ObjectPermissionSerializer(group.permissions.all(), many=True)
        return Response(object_permission.data + permissions.data)

    @extend_schema(
        description="Create group permission.", responses={201: ObjectPermissionSerializer}
    )
    def create(self, request, group_pk):
        """
        Create group permission.
        """
        permission = Permission.objects.get_or_create(**request.data)[0]
        group = Group.objects.get(pk=group_pk)
        group.permissions.add(permission)
        group.save()
        serializer = ObjectPermissionSerializer(permission)
        return Response(serializer.data)

    @extend_schema(
        description="Delete group permission.", responses={200: ObjectPermissionSerializer}
    )
    def destroy(self, request, group_pk):
        """
        Delete group permission.
        """
        permission = Permission.objects.get_or_create(**request.data)[0]
        group = Group.objects.get(pk=group_pk)
        group.permissions.remove(permission)
        group.save()
        serializer = ObjectPermissionSerializer(permission)
        return Response(serializer.data)
