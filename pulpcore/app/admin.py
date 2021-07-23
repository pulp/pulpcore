from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from pulpcore.app.models import Task, RBACContentGuard


@admin.register(Task)
class TaskAdmin(GuardedModelAdmin):
    list_display = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "state",
        "name",
        "started_at",
        "finished_at",
        "error",
        "worker",
        "parent_task",
        "task_group",
    )
    list_filter = (
        "pulp_created",
        "pulp_last_updated",
        "started_at",
        "finished_at",
    )
    raw_id_fields = ("worker",)
    search_fields = ("name",)
    readonly_fields = (
        "pulp_id",
        "pulp_created",
        "pulp_last_updated",
        "state",
        "name",
        "started_at",
        "finished_at",
        "error",
        "worker",
        "parent_task",
        "task_group",
    )


@admin.register(RBACContentGuard)
class RBACContentGuardAdmin(GuardedModelAdmin):
    list_display = (
        "name",
        "description",
    )
    list_filter = (
        "name",
        "pulp_created",
        "pulp_last_updated",
    )
    search_fields = ("name",)
