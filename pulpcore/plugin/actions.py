from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action

from pulpcore.app import tasks
from pulpcore.app.models import Content, RepositoryVersion
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    RepositoryAddRemoveContentSerializer,
)
from pulpcore.tasking.tasks import enqueue_with_reservation


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
        add_content_units = []
        remove_content_units = []
        repository = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if "base_version" in request.data:
            base_version_pk = self.get_resource(request.data["base_version"], RepositoryVersion).pk
        else:
            base_version_pk = None

        if "add_content_units" in request.data:
            for url in request.data["add_content_units"]:
                content = self.get_resource(url, Content)
                add_content_units.append(content.pk)

        if "remove_content_units" in request.data:
            for url in request.data["remove_content_units"]:
                if url == "*":
                    remove_content_units = [url]
                    break
                else:
                    content = self.get_resource(url, Content)
                    remove_content_units.append(content.pk)

        result = enqueue_with_reservation(
            tasks.repository.add_and_remove,
            [repository],
            kwargs={
                "repository_pk": pk,
                "base_version_pk": base_version_pk,
                "add_content_units": add_content_units,
                "remove_content_units": remove_content_units,
            },
        )
        return OperationPostponedResponse(result, request)
