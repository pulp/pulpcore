from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.app.viewsets.base import NamedModelViewSet
from pulpcore.app.serializers.user import UserSerializer, UserObjectPermissionSerializer


class UserViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
):
    endpoint_name = "users"
    serializer_class = UserSerializer
    queryset = User.objects.all()

    @extend_schema(description="List user permissions.",)
    @action(detail=True, methods=["get"], serializer_class=UserObjectPermissionSerializer)
    def permissions(self, request, pk):
        """
        List user permissions.
        """
        user = self.get_object()
        serializer = UserObjectPermissionSerializer(user.userobjectpermission_set.all(), many=True)
        return Response(serializer.data)
