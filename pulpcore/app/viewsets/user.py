from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.app.viewsets.base import NamedModelViewSet
from pulpcore.app.serializers.user import (
    GroupSerializer,
    GroupUserSerializer,
    ObjectPermissionSerializer,
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
    serializer_class = GroupSerializer
    queryset = Group.objects.all()

    @extend_schema(description="List group permissions.",)
    @action(detail=True, methods=["get"], serializer_class=ObjectPermissionSerializer)
    def permissions(self, request, pk):
        """
        List group permissions.
        """
        group = self.get_object()
        object_permission = ObjectPermissionSerializer(
            group.groupobjectpermission_set.all(), many=True
        )
        permissions = ObjectPermissionSerializer(group.permissions.all(), many=True)
        return Response(object_permission.data + permissions.data)

    @extend_schema(description="List group users.",)
    @action(detail=True, methods=["get"], serializer_class=GroupUserSerializer)
    def users(self, request, pk):
        """
        List group users.
        """
        group = self.get_object()
        serializer = GroupUserSerializer(group.user_set.all(), many=True)
        return Response(serializer.data)
