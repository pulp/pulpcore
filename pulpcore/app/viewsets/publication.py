from django_filters.rest_framework import filters, DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins
from rest_framework.filters import OrderingFilter

from pulpcore.app import tasks
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.tasking.tasks import enqueue_with_reservation

from pulpcore.app.models import (
    ContentGuard,
    Distribution,
    Publication,
)
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    ContentGuardSerializer,
    DistributionSerializer,
    PublicationSerializer,
)
from pulpcore.app.viewsets import (
    BaseFilterSet,
    NamedModelViewSet
)
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS


class PublicationViewSet(NamedModelViewSet,
                         mixins.RetrieveModelMixin,
                         mixins.ListModelMixin,
                         mixins.DestroyModelMixin):
    endpoint_name = 'publications'
    queryset = Publication.objects.exclude(complete=False)
    serializer_class = PublicationSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = ('-_created',)


class ContentGuardFilter(BaseFilterSet):
    name = filters.CharFilter()

    class Meta:
        model = ContentGuard
        fields = {
            'name': NAME_FILTER_OPTIONS,
        }


class ContentGuardViewSet(NamedModelViewSet,
                          mixins.CreateModelMixin,
                          mixins.UpdateModelMixin,
                          mixins.DestroyModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.ListModelMixin):
    endpoint_name = 'contentguards'
    serializer_class = ContentGuardSerializer
    queryset = ContentGuard.objects.all()
    filterset_class = ContentGuardFilter


class DistributionFilter(BaseFilterSet):
    # e.g.
    # /?name=foo
    # /?name__in=foo,bar
    # /?base_path__contains=foo
    # /?base_path__icontains=foo
    name = filters.CharFilter()
    base_path = filters.CharFilter()

    class Meta:
        model = Distribution
        fields = {
            'name': NAME_FILTER_OPTIONS,
            'base_path': ['exact', 'contains', 'icontains', 'in']
        }


class DistributionViewSet(NamedModelViewSet,
                          mixins.UpdateModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.ListModelMixin,
                          mixins.DestroyModelMixin):
    """
    Provides read and list methods and also provides asynchronous CUD methods to dispatch tasks
    with reservation that lock all Distributions preventing race conditions during base_path
    checking.
    """
    endpoint_name = 'distributions'
    queryset = Distribution.objects.all()
    serializer_class = DistributionSerializer
    filterset_class = DistributionFilter

    @swagger_auto_schema(operation_description="Trigger an asynchronous create task",
                         responses={202: AsyncOperationResponseSerializer})
    def create(self, request, *args, **kwargs):
        """
        Dispatches a task with reservation for creating a distribution.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        async_result = enqueue_with_reservation(
            tasks.distribution.create,
            "/api/v3/distributions/",
            kwargs={'data': request.data}
        )
        return OperationPostponedResponse(async_result, request)

    @swagger_auto_schema(operation_description="Trigger an asynchronous update task",
                         responses={202: AsyncOperationResponseSerializer})
    def update(self, request, pk, *args, **kwargs):
        """
        Dispatches a task with reservation for updating a distribution.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        async_result = enqueue_with_reservation(
            tasks.distribution.update,
            "/api/v3/distributions/",
            args=(pk,),
            kwargs={'data': request.data, 'partial': partial}
        )
        return OperationPostponedResponse(async_result, request)

    @swagger_auto_schema(operation_description="Trigger an asynchronous partial update task",
                         responses={202: AsyncOperationResponseSerializer})
    def partial_update(self, request, *args, **kwargs):
        """
        Dispatches a task with reservation for partially updating a distribution.
        """
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    @swagger_auto_schema(operation_description="Trigger an asynchronous delete task",
                         responses={202: AsyncOperationResponseSerializer})
    def delete(self, request, pk, *args, **kwargs):
        """
        Dispatches a task with reservation for deleting a distribution.
        """
        self.get_object()
        async_result = enqueue_with_reservation(
            tasks.distribution.delete,
            "/api/v3/distributions/",
            args=(pk,)
        )
        return OperationPostponedResponse(async_result, request)
