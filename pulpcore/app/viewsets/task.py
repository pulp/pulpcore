from gettext import gettext as _

from django.db.models import Prefetch
from django_filters.rest_framework import filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from pulpcore.filters import BaseFilterSet
from pulpcore.app.models import (
    Task,
    TaskGroup,
    TaskSchedule,
    Worker,
    CreatedResource,
    RepositoryVersion,
)
from pulpcore.app.models.role import UserRole
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
from pulpcore.app.util import get_domain
from pulpcore.app.viewsets import NamedModelViewSet, RolesMixin
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NAME_FILTER_OPTIONS
from pulpcore.app.viewsets.custom_filters import (
    ReservedResourcesFilter,
    ReservedResourcesInFilter,
    ReservedResourcesRecordFilter,
    CreatedResourcesFilter,
)
from pulpcore.constants import TASK_INCOMPLETE_STATES, TASK_STATES
from pulpcore.tasking.tasks import dispatch
from pulpcore.tasking.util import cancel_task


class TaskFilter(BaseFilterSet):
    # This filter is deprecated and badly documented, but we need to keep it for compatibility
    # reasons
    reserved_resources_record = ReservedResourcesRecordFilter()
    created_resources = CreatedResourcesFilter()
    # Non model field filters
    reserved_resources = ReservedResourcesFilter(exclusive=True, shared=True)
    reserved_resources__in = ReservedResourcesInFilter(exclusive=True, shared=True)
    exclusive_resources = ReservedResourcesFilter(exclusive=True, shared=False)
    exclusive_resources__in = ReservedResourcesInFilter(exclusive=True, shared=False)
    shared_resources = ReservedResourcesFilter(exclusive=False, shared=True)
    shared_resources__in = ReservedResourcesInFilter(exclusive=False, shared=True)

    class Meta:
        model = Task
        fields = {
            "state": ["exact", "in"],
            "worker": ["exact", "in"],
            "name": ["exact", "contains", "in"],
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
                "condition": "has_model_or_domain_or_obj_perms:core.view_task",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.delete_task",
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.change_task",
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
                "condition": "has_model_or_domain_or_obj_perms:core.manage_roles_task",
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

    def get_serializer(self, *args, **kwargs):
        """Set repo_ver_mapping in serializer context for optimized serialization."""
        many = kwargs.get("many", False)
        serializer = super().get_serializer(*args, **kwargs)
        # Perform optimization for list & retrieve actions and only during **full** serialization
        # "swagger_fake_view" is set when drf_spectacular is building the OpenAPI spec
        if (
            self.action in ("list", "retrieve")
            and self.get_serializer_class() == TaskSerializer
            and not getattr(self, "swagger_fake_view", False)
        ):
            task_list = args[0] if many else [args[0]]
            created_resources = [cr for task in task_list for cr in task.created_resources.all()]
            # Optimization for RepositoryVersion created_resources
            repo_ver_pks = [
                cr.object_id
                for cr in created_resources
                if issubclass(cr.content_type.model_class(), RepositoryVersion)
            ]
            repo_vers = (
                RepositoryVersion.objects.select_related("repository")
                .filter(pk__in=repo_ver_pks, complete=True)
                .only("pk", "number", "repository__pulp_type")
            )
            serializer.context["repo_ver_mapping"] = {rv.pk: rv for rv in repo_vers}
            # Assume, all tasks and related resources are of the same domain.
            serializer.context["pulp_domain"] = get_domain()
            # Optimization for User created_by
            task_pks = [t.pk for t in task_list]
            user_roles = UserRole.objects.filter(
                role__name="core.task_owner", object_id__in=task_pks
            ).order_by("-pulp_created")
            serializer.context["task_user_mapping"] = {u.object_id: u.user_id for u in user_roles}
        return serializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ("list", "retrieve"):
            qs = qs.prefetch_related(
                "progress_reports",
                Prefetch(
                    "created_resources",
                    queryset=CreatedResource.objects.select_related("content_type"),
                ),
                Prefetch("child_tasks", queryset=Task.objects.only("pk")),
            )
        return qs

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
            " to a specified timestamp."
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


class TaskGroupViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    queryset = TaskGroup.objects.all()
    endpoint_name = "task-groups"
    serializer_class = TaskGroupSerializer
    ordering = "-pulp_created"


class WorkerFilter(BaseFilterSet):
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


class TaskScheduleViewSet(
    NamedModelViewSet,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    RolesMixin,
):
    """
    ViewSet to monitor task schedules.
    """

    queryset = TaskSchedule.objects.all()
    endpoint_name = "task-schedules"
    filterset_fields = {
        "name": ["exact", "contains"],
        "task_name": ["exact", "contains"],
    }
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
                "condition": "has_model_or_domain_or_obj_perms:core.view_taskschedule",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.manage_roles_taskschedule",
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
