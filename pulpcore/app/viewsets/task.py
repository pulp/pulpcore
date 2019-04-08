from django_filters.rest_framework import filters, DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, mixins
from rest_framework.decorators import detail_route
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from pulpcore.constants import TASK_INCOMPLETE_STATES

from pulpcore.app.models import Task, Worker
from pulpcore.app.serializers import MinimalTaskSerializer, TaskSerializer, WorkerSerializer
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS, DATETIME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import HyperlinkRelatedFilter, IsoDateTimeFilter
from pulpcore.tasking.util import cancel as cancel_task


class TaskFilter(BaseFilterSet):
    state = filters.CharFilter()
    worker = HyperlinkRelatedFilter()
    name = filters.CharFilter()
    started_at = IsoDateTimeFilter(field_name='started_at')
    finished_at = IsoDateTimeFilter(field_name='finished_at')
    parent = HyperlinkRelatedFilter()

    class Meta:
        model = Task
        fields = {
            'state': ['exact', 'in'],
            'worker': ['exact', 'in'],
            'name': ['contains'],
            'started_at': DATETIME_FILTER_OPTIONS,
            'finished_at': DATETIME_FILTER_OPTIONS,
            'parent': ['exact']
        }


class TaskViewSet(NamedModelViewSet,
                  mixins.RetrieveModelMixin,
                  mixins.ListModelMixin,
                  mixins.DestroyModelMixin):
    queryset = Task.objects.all()
    endpoint_name = 'tasks'
    filterset_class = TaskFilter
    serializer_class = TaskSerializer
    minimal_serializer_class = MinimalTaskSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = ('-_created')

    @swagger_auto_schema(operation_description="This operation cancels a task.",
                         operation_summary="Cancel a task")
    @detail_route(methods=('post',))
    def cancel(self, request, pk=None):
        task = self.get_object()
        cancel_task(task.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, pk=None):
        task = self.get_object()
        if task.state in TASK_INCOMPLETE_STATES:
            return Response(status=status.HTTP_409_CONFLICT)
        return super().destroy(request, pk)


class WorkerFilter(BaseFilterSet):
    name = filters.CharFilter()
    last_heartbeat = IsoDateTimeFilter()
    online = filters.BooleanFilter(method='filter_online')
    missing = filters.BooleanFilter(method='filter_missing')

    class Meta:
        model = Worker
        fields = {
            'name': NAME_FILTER_OPTIONS,
            'last_heartbeat': DATETIME_FILTER_OPTIONS,
            'online': ['exact'],
            'missing': ['exact']
        }

    def filter_online(self, queryset, name, value):
        online_workers = Worker.objects.online_workers()

        if value:
            return queryset.filter(pk__in=online_workers)
        else:
            return queryset.exclude(pk__in=online_workers)

    def filter_missing(self, queryset, name, value):
        missing_workers = Worker.objects.missing_workers()

        if value:
            return queryset.filter(pk__in=missing_workers)
        else:
            return queryset.exclude(pk__in=missing_workers)


class WorkerViewSet(NamedModelViewSet,
                    mixins.RetrieveModelMixin,
                    mixins.ListModelMixin):
    queryset = Worker.objects.all()
    serializer_class = WorkerSerializer
    endpoint_name = 'workers'
    http_method_names = ['get', 'options']
    lookup_value_regex = '[^/]+'
    filterset_class = WorkerFilter
