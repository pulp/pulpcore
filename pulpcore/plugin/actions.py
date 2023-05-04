from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from pulpcore.app import tasks
from pulpcore.app.models import RepositoryVersion
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    RepositoryAddRemoveContentSerializer,
)
from pulpcore.tasking.tasks import dispatch


__all__ = ["ModifyRepositoryActionMixin"]


class ModifyRepositoryActionMixin:
    @extend_schema(
        description="Trigger an asynchronous task to create a new repository version.",
        summary="Modify Repository Content",
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"], serializer_class=RepositoryAddRemoveContentSerializer)
    def modify(self, request, pk):
        """
        Queues a task that creates a new RepositoryVersion by adding and removing content units
        """
        repository = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if "base_version" in request.data:
            base_version_pk = self.get_resource(request.data["base_version"], RepositoryVersion).pk
        else:
            base_version_pk = None

        task = dispatch(
            tasks.repository.add_and_remove,
            exclusive_resources=[repository],
            kwargs={
                "repository_pk": pk,
                "base_version_pk": base_version_pk,
                "add_content_units": serializer.validated_data.get("add_content_units", []),
                "remove_content_units": serializer.validated_data.get("remove_content_units", []),
            },
        )
        return OperationPostponedResponse(task, request)
