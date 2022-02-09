from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import (
    GroupProgressReportSerializer,
    IdentityField,
    ModelSerializer,
    ProgressReportSerializer,
    RelatedField,
    RelatedResourceField,
    TaskGroupStatusCountField,
)
from pulpcore.constants import TASK_STATES


class CreatedResourceSerializer(RelatedResourceField):
    class Meta:
        model = models.CreatedResource
        fields = []


class TaskSerializer(ModelSerializer):
    pulp_href = IdentityField(view_name="tasks-detail")
    state = serializers.CharField(
        help_text=_(
            "The current state of the task. The possible values include:"
            " 'waiting', 'skipped', 'running', 'completed', 'failed', 'canceled' and 'canceling'."
        ),
        read_only=True,
    )
    name = serializers.CharField(help_text=_("The name of task."))
    logging_cid = serializers.CharField(
        help_text=_("The logging correlation id associated with this task")
    )
    started_at = serializers.DateTimeField(
        help_text=_("Timestamp of the when this task started execution."), read_only=True
    )
    finished_at = serializers.DateTimeField(
        help_text=_("Timestamp of the when this task stopped execution."), read_only=True
    )
    error = serializers.DictField(
        child=serializers.JSONField(),
        help_text=_(
            "A JSON Object of a fatal error encountered during the execution of this task."
        ),
        read_only=True,
    )
    worker = RelatedField(
        help_text=_(
            "The worker associated with this task."
            " This field is empty if a worker is not yet assigned."
        ),
        read_only=True,
        view_name="workers-detail",
    )
    parent_task = RelatedField(
        help_text=_("The parent task that spawned this task."),
        read_only=True,
        view_name="tasks-detail",
    )
    child_tasks = RelatedField(
        help_text=_("Any tasks spawned by this task."),
        many=True,
        read_only=True,
        view_name="tasks-detail",
    )
    task_group = RelatedField(
        help_text=_("The task group that this task is a member of."),
        read_only=True,
        view_name="task-groups-detail",
    )
    progress_reports = ProgressReportSerializer(many=True, read_only=True)
    created_resources = CreatedResourceSerializer(
        help_text=_("Resources created by this task."),
        many=True,
        read_only=True,
        view_name="None",  # This is a polymorphic field. The serializer does not need a view name.
    )
    reserved_resources_record = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("A list of resources required by that task."),
        read_only=True,
    )

    class Meta:
        model = models.Task
        fields = ModelSerializer.Meta.fields + (
            "state",
            "name",
            "logging_cid",
            "started_at",
            "finished_at",
            "error",
            "worker",
            "parent_task",
            "child_tasks",
            "task_group",
            "progress_reports",
            "created_resources",
            "reserved_resources_record",
        )


class MinimalTaskSerializer(TaskSerializer):
    class Meta:
        model = models.Task
        fields = ModelSerializer.Meta.fields + (
            "name",
            "state",
            "started_at",
            "finished_at",
            "worker",
        )


class TaskGroupSerializer(ModelSerializer):
    pulp_href = IdentityField(view_name="task-groups-detail")
    description = serializers.CharField(help_text=_("A description of the task group."))
    all_tasks_dispatched = serializers.BooleanField(
        help_text=_("Whether all tasks have been spawned for this task group.")
    )

    waiting = TaskGroupStatusCountField(
        state=TASK_STATES.WAITING, help_text=_("Number of tasks in the 'waiting' state")
    )
    skipped = TaskGroupStatusCountField(
        state=TASK_STATES.SKIPPED, help_text=_("Number of tasks in the 'skipped' state")
    )
    running = TaskGroupStatusCountField(
        state=TASK_STATES.RUNNING, help_text=_("Number of tasks in the 'running' state")
    )
    completed = TaskGroupStatusCountField(
        state=TASK_STATES.COMPLETED, help_text=_("Number of tasks in the 'completed' state")
    )
    canceled = TaskGroupStatusCountField(
        state=TASK_STATES.CANCELED, help_text=_("Number of tasks in the 'canceled' state")
    )
    failed = TaskGroupStatusCountField(
        state=TASK_STATES.FAILED, help_text=_("Number of tasks in the 'failed' state")
    )
    canceling = TaskGroupStatusCountField(
        state=TASK_STATES.CANCELING, help_text=_("Number of tasks in the 'canceling' state")
    )
    group_progress_reports = GroupProgressReportSerializer(many=True, read_only=True)
    tasks = MinimalTaskSerializer(many=True, read_only=True)

    class Meta:
        model = models.TaskGroup
        fields = (
            "pulp_href",
            "description",
            "all_tasks_dispatched",
            "waiting",
            "skipped",
            "running",
            "completed",
            "canceled",
            "failed",
            "canceling",
            "group_progress_reports",
            "tasks",
        )


class TaskCancelSerializer(ModelSerializer):
    state = serializers.CharField(
        help_text=_("The desired state of the task. Only 'canceled' is accepted."),
    )

    class Meta:
        model = models.Task
        fields = ("state",)


class ContentAppStatusSerializer(ModelSerializer):
    name = serializers.CharField(help_text=_("The name of the worker."), read_only=True)
    last_heartbeat = serializers.DateTimeField(
        help_text=_("Timestamp of the last time the worker talked to the service."), read_only=True
    )

    class Meta:
        model = models.ContentAppStatus
        fields = ("name", "last_heartbeat")


class WorkerSerializer(ModelSerializer):
    pulp_href = IdentityField(view_name="workers-detail")

    name = serializers.CharField(help_text=_("The name of the worker."), read_only=True)
    last_heartbeat = serializers.DateTimeField(
        help_text=_("Timestamp of the last time the worker talked to the service."), read_only=True
    )
    current_task = RelatedField(
        help_text=_(
            "The task this worker is currently executing, or empty if the worker is not "
            "currently assigned to a task."
        ),
        read_only=True,
        view_name="tasks-detail",
    )

    class Meta:
        model = models.Worker
        fields = ModelSerializer.Meta.fields + ("name", "last_heartbeat", "current_task")


class TaskScheduleSerializer(ModelSerializer):
    pulp_href = IdentityField(view_name="task-schedules-detail")
    name = serializers.CharField(help_text=_("The name of the task schedule."), allow_blank=False)
    task_name = serializers.CharField(help_text=_("The name of the task to be scheduled."))
    dispatch_interval = serializers.DurationField(help_text=_("Periodicity of the schedule."))
    next_dispatch = serializers.DateTimeField(
        help_text=_("Timestamp of the next time the task will be dispatched."), read_only=True
    )
    last_task = RelatedField(
        help_text=_("The last task dispatched by this schedule."),
        read_only=True,
        view_name="tasks-detail",
    )

    class Meta:
        model = models.TaskSchedule
        fields = ModelSerializer.Meta.fields + (
            "name",
            "task_name",
            "dispatch_interval",
            "next_dispatch",
            "last_task",
        )
