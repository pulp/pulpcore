from gettext import gettext as _

from django_filters.rest_framework import filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action

from pulpcore.app import tasks
from pulpcore.app.models import AlternateContentSource
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    AlternateContentSourceSerializer,
)
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.viewsets import (
    AsyncUpdateMixin,
    BaseFilterSet,
    NamedModelViewSet,
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.tasking.tasks import dispatch


class AlternateContentSourceFilter(BaseFilterSet):
    """FilterSet for ACS."""

    name = filters.CharFilter()

    class Meta:
        model = AlternateContentSource
        fields = {
            "name": NAME_FILTER_OPTIONS,
        }


class AlternateContentSourceViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    AsyncUpdateMixin,
    NamedModelViewSet,
):
    """
    A class for ACS viewset.
    """

    queryset = AlternateContentSource.objects.all()
    serializer_class = AlternateContentSourceSerializer
    endpoint_name = "acs"
    router_lookup = "acs"
    filterset_class = AlternateContentSourceFilter

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        raise NotImplementedError(_("Method not implemented by plugin writer!"))

    @extend_schema(
        description="Trigger an asynchronous delete ACS task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def destroy(self, request, pk, **kwargs):
        acs = self.get_object()
        reservations = []
        instance_ids = []

        for path in acs.paths.all():
            if path.repository_id:
                instance_ids.append(
                    (str(path.repository_id), "core", "RepositorySerializer"),
                )
        reservations.append(acs)
        instance_ids.append(
            (str(acs.pk), "core", "AlternateContentSourceSerializer"),
        )
        async_result = dispatch(
            tasks.base.general_multi_delete, exclusive_resources=reservations, args=(instance_ids,)
        )
        return OperationPostponedResponse(async_result, request)
