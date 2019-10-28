from drf_yasg.utils import swagger_auto_schema

from django.db.utils import IntegrityError

from pulpcore.app import tasks
from pulpcore.plugin.serializers import (
    ArtifactSerializer,
    AsyncOperationResponseSerializer,
)
from pulpcore.plugin.models import Artifact
from pulpcore.plugin.tasking import enqueue_with_reservation
from pulpcore.plugin.viewsets import (
    ContentViewSet,
    OperationPostponedResponse,
)


class SingleArtifactContentUploadViewSet(ContentViewSet):
    """A base ContentViewSet with added upload functionality."""

    def get_deferred_context(self, request):
        """Supply context for deferred validation.

        When overwriting this method, it must return a dict, that is serializable by rq
        and does _not_ contain 'request' as a key.
        """
        return {}

    @swagger_auto_schema(
        operation_description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """
        Create a content unit.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        artifact = serializer.validated_data["artifact"]
        repository = serializer.validated_data.get("repository")

        task_payload = {k: v for k, v in request.data.items()}
        if task_payload.pop("file", None):
            # in the upload code path make sure, the artifact exists, and the 'file'
            # parameter is replaced by 'artifact'
            try:
                artifact.save()
            except IntegrityError:
                # if artifact already exists, let's use it
                artifact = Artifact.objects.get(sha256=artifact.sha256)
            task_payload["artifact"] = ArtifactSerializer(
                artifact, context={"request": request}
            ).data["pulp_href"]

        shared_resources = [artifact]
        if repository:
            shared_resources.append(repository)

        app_label = self.queryset.model._meta.app_label
        async_result = enqueue_with_reservation(
            tasks.base.general_create,
            shared_resources,
            args=(app_label, serializer.__class__.__name__),
            kwargs={
                "data": task_payload,
                "context": self.get_deferred_context(request),
            },
        )
        return OperationPostponedResponse(async_result, request)
