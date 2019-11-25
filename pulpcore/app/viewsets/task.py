from gettext import gettext as _

from django_filters.rest_framework import DjangoFilterBackend, filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins, status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.app.models import Task, Worker
from pulpcore.app.serializers import (
    MinimalTaskSerializer,
    TaskCancelSerializer,
    TaskSerializer,
    WorkerSerializer,
)
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    HyperlinkRelatedFilter,
    IsoDateTimeFilter,
    ReservedResourcesFilter,
    CreatedResourcesFilter,
)
from pulpcore.constants import TASK_INCOMPLETE_STATES
from pulpcore.tasking.util import cancel as cancel_task


class TaskFilter(BaseFilterSet):
    state = filters.CharFilter()
    worker = HyperlinkRelatedFilter()
    name = filters.CharFilter()
    started_at = IsoDateTimeFilter(field_name='started_at')
    finished_at = IsoDateTimeFilter(field_name='finished_at')
    parent = HyperlinkRelatedFilter()
    reserved_resources_record = ReservedResourcesFilter()
    created_resources = CreatedResourcesFilter()

    class Meta:
        model = Task
        fields = {
            'state': ['exact', 'in'],
            'worker': ['exact', 'in'],
            'name': ['contains'],
            'started_at': DATETIME_FILTER_OPTIONS,
            'finished_at': DATETIME_FILTER_OPTIONS,
            'reserved_resources_record': ['exact'],
            'created_resources': ['exact']
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
    ordering = ('-pulp_created')

    @swagger_auto_schema(operation_description="This operation cancels a task.",
                         operation_summary="Cancel a task", operation_id='tasks_cancel',
                         responses={200: TaskSerializer})
    def partial_update(self, request, pk=None, partial=True):
        task = self.get_object()
        if 'state' not in request.data:
            raise ValidationError(_("'state' must be provided with the request."))
        if request.data['state'] != 'canceled':
            raise ValidationError(_("The only acceptable value for 'state' is 'canceled'."))
        task = cancel_task(task.pk)
        serializer = self.serializer_class(task, context={'request': request})
        return Response(serializer.data)

    def destroy(self, request, pk=None):
        task = self.get_object()
        if task.state in TASK_INCOMPLETE_STATES:
            return Response(status=status.HTTP_409_CONFLICT)
        return super().destroy(request, pk)

    def get_serializer_class(self):
        if self.action == 'partial_update':
            return TaskCancelSerializer
        return super().get_serializer_class()


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
