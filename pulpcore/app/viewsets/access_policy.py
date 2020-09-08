from rest_framework import mixins


from pulpcore.app.models import AccessPolicy
from pulpcore.app.serializers import AccessPolicySerializer
from pulpcore.app.viewsets import NamedModelViewSet


class AccessPolicyViewSet(
    NamedModelViewSet, mixins.UpdateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin
):
    """
    ViewSet for AccessPolicy.

    NOTE: This API endpoint is in "tech preview" and subject to change

    """

    queryset = AccessPolicy.objects.all()
    serializer_class = AccessPolicySerializer
    endpoint_name = "access_policies"
    ordering = "viewset_name"
