"""
ViewSet for replicating repositories and distributions from an upstream Pulp
"""
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action

from pulpcore.app.models import TaskGroup, UpstreamPulp
from pulpcore.app.serializers import AsyncOperationResponseSerializer, UpstreamPulpSerializer
from pulpcore.app.viewsets import NamedModelViewSet
from pulpcore.app.response import TaskGroupOperationResponse
from pulpcore.app.tasks import replicate_distributions
from pulpcore.tasking.tasks import dispatch


class UpstreamPulpViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    mixins.UpdateModelMixin,
):
    """API for configuring an upstream Pulp to replicate. This API is provided as a tech preview."""

    queryset = UpstreamPulp.objects.all()
    endpoint_name = "upstream-pulps"
    serializer_class = UpstreamPulpSerializer
    ordering = "-pulp_created"

    @extend_schema(
        summary="Replicate",
        description="Trigger an asynchronous repository replication task group. This API is "
        "provided as a tech preview.",
        request=None,
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def replicate(self, request, pk):
        """
        Triggers an asynchronous repository replication operation.
        """
        server = UpstreamPulp.objects.get(pk=pk)
        task_group = TaskGroup.objects.create(description=f"Replication of {server.name}")

        uri = "/api/v3/servers/"
        if settings.DOMAIN_ENABLED:
            uri = f"/{request.domain.name}{uri}"

        dispatch(
            replicate_distributions,
            exclusive_resources=[uri],
            kwargs={"server_pk": pk},
            task_group=task_group,
        )

        return TaskGroupOperationResponse(task_group, request)
