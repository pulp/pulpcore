from gettext import gettext as _

from django_filters.rest_framework import filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.app.models import Task, TaskGroup, TaskSchedule, Worker
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    MinimalTaskSerializer,
    PurgeSerializer,
    TaskCancelSerializer,
    TaskGroupSerializer,
    TaskScheduleSerializer,
    TaskSerializer,
    WorkerSerializer,
)
from pulpcore.app.tasks import purge
from pulpcore.app.viewsets import BaseFilterSet, NamedModelViewSet, RolesMixin
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    HyperlinkRelatedFilter,
    IsoDateTimeFilter,
    ReservedResourcesFilter,
    CreatedResourcesFilter,
)
from pulpcore.constants import TASK_INCOMPLETE_STATES, TASK_STATES, TASK_CHOICES
from pulpcore.tasking.tasks import dispatch
from pulpcore.tasking.util import cancel as cancel_task


class TaskFilter(BaseFilterSet):
    state = filters.ChoiceFilter(choices=TASK_CHOICES)
    worker = HyperlinkRelatedFilter()
    name = filters.CharFilter()
    logging_cid = filters.CharFilter()
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
            "state": ["exact", "in"],
            "worker": ["exact", "in"],
            "name": ["contains"],
            "logging_cid": ["exact", "contains"],
            "started_at": DATETIME_FILTER_OPTIONS,
            "finished_at": DATETIME_FILTER_OPTIONS,
            "parent_task": ["exact"],
            "child_tasks": ["exact"],
            "task_group": ["exact"],
            "reserved_resources_record": ["exact"],
            "created_resources": ["exact"],
        }


class TaskViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    RolesMixin,
):
    queryset = Task.objects.all()
    endpoint_name = "tasks"
    filterset_class = TaskFilter
    serializer_class = TaskSerializer
    minimal_serializer_class = MinimalTaskSerializer
    ordering = "-pulp_created"
    queryset_filtering_required_permission = "core.view_task"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {"action": ["list"], "principal": "authenticated", "effect": "allow"},
            {
                "action": ["retrieve", "my_permissions"],
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
            # 'purge' is filtered by current-user and core.delete_task permissions at the queryset
            # level, and needs no extra protections here
            {
                "action": ["purge"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.manage_roles_task",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.task_owner"},
            }
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.task_owner": {
            "description": "Allow all actions on a task.",
            "permissions": [
                "core.view_task",
                "core.change_task",
                "core.delete_task",
                "core.manage_roles_task",
            ],
        },
        "core.task_viewer": ["core.view_task"],
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
        http_status = (
            None
            if task.state in [TASK_STATES.CANCELING, TASK_STATES.CANCELED]
            else status.HTTP_409_CONFLICT
        )
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

    @extend_schema(
        description=(
            "Trigger an asynchronous task that deletes completed tasks that finished prior"
            " to a specified timestamp (tech-preview, may change in the future)."
        ),
        summary="Purge Completed Tasks",
        operation_id="tasks_purge",
        request=PurgeSerializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=False, methods=["post"])
    def purge(self, request):
        """
        Purge task-records for tasks in 'final' states.
        """
        serializer = PurgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = dispatch(
            purge, args=[serializer.data["finished_before"], list(serializer.data["states"])]
        )
        return OperationPostponedResponse(task, request)


class TaskGroupFilter(BaseFilterSet):
    class Meta:
        model = TaskGroup
        fields = ()


class TaskGroupViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    queryset = TaskGroup.objects.all()
    endpoint_name = "task-groups"
    filterset_class = TaskGroupFilter
    serializer_class = TaskGroupSerializer
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


class TaskScheduleFilter(BaseFilterSet):
    name = filters.CharFilter()
    task_name = filters.CharFilter()

    class Meta:
        model = TaskSchedule
        fields = {
            "name": ["exact", "contains"],
            "task_name": ["exact", "contains"],
        }


class TaskScheduleViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    RolesMixin,
):
    """
    ViewSet to monitor task schedules.

    NOTE: This feature is in tech-preview and may change in backwards incompatible ways.
    """

    queryset = TaskSchedule.objects.all()
    endpoint_name = "task-schedules"
    filterset_class = TaskScheduleFilter
    serializer_class = TaskScheduleSerializer
    ordering = "-pulp_created"
    queryset_filtering_required_permission = "core.view_taskschedule"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {"action": ["list"], "principal": "authenticated", "effect": "allow"},
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_taskschedule",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.manage_roles_taskschedule",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.taskschedule_owner"},
            }
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "core.taskschedule_owner": {
            "description": "Allow all actions on a taskschedule.",
            "permissions": [
                "core.view_taskschedule",
                "core.manage_roles_taskschedule",
            ],
        },
        "core.taskschedule_viewer": ["core.view_taskschedule"],
    }
