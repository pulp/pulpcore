"""
ViewSet for replicating repositories and distributions from an upstream Pulp
"""

from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action

from pulpcore.app.models import TaskGroup, UpstreamPulp
from pulpcore.app.serializers import TaskGroupOperationResponseSerializer, UpstreamPulpSerializer
from pulpcore.app.viewsets import NamedModelViewSet, RolesMixin
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
    RolesMixin,
):
    """API for configuring an upstream Pulp to replicate. This API is provided as a tech preview."""

    queryset = UpstreamPulp.objects.all()
    endpoint_name = "upstream-pulps"
    serializer_class = UpstreamPulpSerializer
    ordering = "-pulp_created"
    queryset_filtering_required_permission = "core.view_upstreampulp"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_perms:core.add_upstreampulp",
                ],
            },
            {
                "action": ["retrieve"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:core.view_upstreampulp",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.delete_upstreampulp",
                ],
            },
            {
                "action": ["update", "partial_update"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.change_upstreampulp",
                ],
            },
            {
                "action": ["replicate"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": [
                    "has_model_or_domain_or_obj_perms:core.replicate_upstreampulp",
                ],
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_domain_or_obj_perms:core.manage_roles_upstreampulp"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.upstreampulp_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "core.upstreampulp_creator": ["core.add_upstreampulp"],
        "core.upstreampulp_owner": [
            "core.view_upstreampulp",
            "core.change_upstreampulp",
            "core.delete_upstreampulp",
            "core.replicate_upstreampulp",
            "core.manage_roles_upstreampulp",
        ],
        "core.upstreampulp_viewer": ["core.view_upstreampulp"],
        "core.upstreampulp_user": [
            "core.view_upstreampulp",
            "core.replicate_upstreampulp",
        ],
    }

    @extend_schema(
        summary="Replicate",
        description="Trigger an asynchronous repository replication task group. This API is "
        "provided as a tech preview.",
        request=None,
        responses={202: TaskGroupOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def replicate(self, request, pk):
        """
        Triggers an asynchronous repository replication operation.
        """
        server = UpstreamPulp.objects.get(pk=pk)
        task_group = TaskGroup.objects.create(description=f"Replication of {server.name}")

        exclusive_resources = [f"pdrn:{request.pulp_domain.pulp_id}:servers"]

        dispatch(
            replicate_distributions,
            exclusive_resources=exclusive_resources,
            kwargs={"server_pk": pk},
            task_group=task_group,
        )

        return TaskGroupOperationResponse(task_group, request)
