from gettext import gettext as _

from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from pulpcore.filters import BaseFilterSet
from pulpcore.app.models import Domain
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    DomainSerializer,
    DomainBackendMigratorSerializer,
    AsyncOperationResponseSerializer,
)
from pulpcore.app.tasks import migrate_backend
from pulpcore.app.viewsets import NamedModelViewSet, AsyncRemoveMixin, AsyncUpdateMixin
from pulpcore.app.viewsets.base import NAME_FILTER_OPTIONS
from pulpcore.tasking.tasks import dispatch


class DomainFilter(BaseFilterSet):
    """FilterSet for Domain."""

    class Meta:
        model = Domain
        fields = {"name": NAME_FILTER_OPTIONS}


class DomainViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    AsyncUpdateMixin,
    AsyncRemoveMixin,
):
    """
    ViewSet for Domain.

    NOTE: This API endpoint is in "tech preview" and subject to change
    """

    queryset = Domain.objects.all()
    serializer_class = DomainSerializer
    endpoint_name = "domains"
    filterset_class = DomainFilter
    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
            {
                "action": ["create"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_perms:core.add_domain",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_domain",
            },
            {
                "action": ["update", "partial_update", "migrate"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.change_domain",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.delete_domain",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.manage_roles_domain",
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": ["core.domain_owner"]},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    # There is probably more locked roles needed for this feature
    LOCKED_ROLES = {
        "core.domain_creator": ["core.add_domain"],
        "core.domain_owner": [
            "core.view_domain",
            "core.change_domain",
            "core.delete_domain",
            "core.manage_roles_domain",
        ],
        "core.domain_viewer": ["core.view_domain"],
    }

    @extend_schema(
        description="Trigger an asynchronous update task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def update(self, request, pk, **kwargs):
        """Prevent trying to update the default domain."""
        instance = self.get_object()
        if instance.name == "default":
            raise ValidationError(_("Default domain can not be updated."))

        return super().update(request, pk, **kwargs)

    @extend_schema(
        description="Trigger an asynchronous delete task",
        responses={202: AsyncOperationResponseSerializer},
    )
    def destroy(self, request, pk, **kwargs):
        """Prevent trying to delete the default domain."""
        instance = self.get_object()
        if instance.name == "default":
            raise ValidationError(_("Default domain can not be deleted."))

        return super().destroy(request, pk, **kwargs)

    @extend_schema(
        summary="Migrate storage backend",
        request=DomainBackendMigratorSerializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=False, methods=["post"])
    def migrate(self, request, **kwargs):
        """
        Migrate the domain's storage backend to a new one.

        Launches a background task to copy the domain's artifacts over to the supplied storage
        backend. Then updates the domain's storage settings to the new storage backend. This task
        does not delete the stored files of the artifacts from the previous backend.

        **IMPORTANT** This task will block all other tasks within the domain until the migration is
        completed, essentially putting the domain into a read only state. Content will still be
        served from the old storage backend until the migration has completed, so don't remove
        the old backend until then. Note, this endpoint is not allowed on the default domain.

        This feature is in Tech Preview and is subject to future change and thus not guaranteed to
        be backwards compatible.
        """
        instance = request.pulp_domain
        data = request.data
        if instance.name == "default":
            raise ValidationError(_("Default domain can not be migrated."))
        serializer = DomainBackendMigratorSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        task = dispatch(
            migrate_backend,
            args=(data,),
            exclusive_resources=[instance],
        )
        return OperationPostponedResponse(task, request)
