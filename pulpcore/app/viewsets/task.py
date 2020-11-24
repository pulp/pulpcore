from gettext import gettext as _

from django_filters.rest_framework import DjangoFilterBackend, filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.app.access_policy import AccessPolicyFromDB
from pulpcore.app.models import Task, TaskGroup, Worker
from pulpcore.app.serializers import (
    MinimalTaskSerializer,
    TaskCancelSerializer,
    TaskSerializer,
    WorkerSerializer,
    TaskGroupSerializer,
)
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    HyperlinkRelatedFilter,
    IsoDateTimeFilter,
    ReservedResourcesFilter,
    CreatedResourcesFilter,
)
from pulpcore.constants import TASK_INCOMPLETE_STATES, TASK_STATES
from pulpcore.tasking.util import cancel as cancel_task


class TaskFilter(BaseFilterSet):
    state = filters.CharFilter()
    worker = HyperlinkRelatedFilter()
    name = filters.CharFilter()
    started_at = IsoDateTimeFilter(field_name="started_at")
    finished_at = IsoDateTimeFilter(field_name="finished_at")
    parent_task = HyperlinkRelatedFilter()
    child_tasks = HyperlinkRelatedFilter()
    task_group = HyperlinkRelatedFilter()
    reserved_resources_record = ReservedResourcesFilter()
    created_resources = CreatedResourcesFilter()

    class Meta:
        model = Task
        fields = {
            "name": ["contains"],
            "state": ["exact", "in"],
            "worker": ["exact", "in"],
            "started_at": DATETIME_FILTER_OPTIONS,
            "finished_at": DATETIME_FILTER_OPTIONS,
            "parent_task": ["exact"],
            "child_tasks": ["exact"],
            "task_group": ["exact"],
            "reserved_resources_record": ["exact"],
            "created_resources": ["exact"],
        }


class TaskViewSet(
    NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin, mixins.DestroyModelMixin
):
    queryset = Task.objects.all()
    endpoint_name = "tasks"
    filterset_class = TaskFilter
    serializer_class = TaskSerializer
    minimal_serializer_class = MinimalTaskSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = "-pulp_created"
    permission_classes = (AccessPolicyFromDB,)
    queryset_filtering_required_permission = "core.view_task"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {"action": ["list"], "principal": "authenticated", "effect": "allow"},
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_task",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.delete_task",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.change_task",
            },
        ],
        "permissions_assignment": [
            {
                "function": "add_for_object_creator",
                "parameters": None,
                "permissions": ["core.view_task", "core.change_task", "core.delete_task"],
            }
        ],
    }

    @extend_schema(
        description="This operation cancels a task.",
        summary="Cancel a task",
        operation_id="tasks_cancel",
        responses={200: TaskSerializer, 409: TaskSerializer},
    )
    def partial_update(self, request, pk=None, partial=True):
        task = self.get_object()
        if "state" not in request.data:
            raise ValidationError(_("'state' must be provided with the request."))
        if request.data["state"] != "canceled":
            raise ValidationError(_("The only acceptable value for 'state' is 'canceled'."))
        task = cancel_task(task.pk)
        # Check whether task is actually canceled
        http_status = None if task.state == TASK_STATES.CANCELED else status.HTTP_409_CONFLICT
        serializer = self.serializer_class(task, context={"request": request})
        return Response(serializer.data, status=http_status)

    def destroy(self, request, pk=None):
        task = self.get_object()
        if task.state in TASK_INCOMPLETE_STATES:
            return Response(status=status.HTTP_409_CONFLICT)
        return super().destroy(request, pk)

    def get_serializer_class(self):
        if self.action == "partial_update":
            return TaskCancelSerializer
        return super().get_serializer_class()


class TaskGroupFilter(BaseFilterSet):
    class Meta:
        model = TaskGroup
        fields = ()


class TaskGroupViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    queryset = TaskGroup.objects.all()
    endpoint_name = "task-groups"
    filterset_class = TaskGroupFilter
    serializer_class = TaskGroupSerializer
    filter_backends = (OrderingFilter, DjangoFilterBackend)
    ordering = "-pulp_created"


class WorkerFilter(BaseFilterSet):
    name = filters.CharFilter()
    last_heartbeat = IsoDateTimeFilter()
    online = filters.BooleanFilter(method="filter_online")
    missing = filters.BooleanFilter(method="filter_missing")

    class Meta:
        model = Worker
        fields = {
            "name": NAME_FILTER_OPTIONS,
            "last_heartbeat": DATETIME_FILTER_OPTIONS,
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


class WorkerViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    queryset = Worker.objects.all()
    serializer_class = WorkerSerializer
    endpoint_name = "workers"
    http_method_names = ["get", "options"]
    lookup_value_regex = "[^/]+"
    filterset_class = WorkerFilter
