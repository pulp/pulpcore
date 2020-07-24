from collections import namedtuple

from drf_spectacular.utils import extend_schema

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

ContentUploadData = namedtuple("ContentUploadData", ["shared_resources", "task_payload"])


class ContentUploadViewSet(ContentViewSet):
    """A base ContentViewSet with added upload functionality."""

    def __init__(self, *args, **kwargs):
        """Set a default task's type that creates a new content from an uploaded Artifact."""
        super().__init__(*args, **kwargs)
        self._task_function_type = tasks.base.general_create

    def get_deferred_context(self, request):
        """
        Supply context for deferred validation.

        When overwriting this method, it must return a dict, that is serializable by rq
        and does _not_ contain 'request' as a key.
        """
        return {}

    @extend_schema(
        description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """Create a content unit."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_data = self.init_content_data(serializer, request)

        repository = serializer.validated_data.get("repository")
        if repository:
            content_data.shared_resources.append(repository)

        app_label = self.queryset.model._meta.app_label
        async_result = enqueue_with_reservation(
            self._task_function_type,
            content_data.shared_resources,
            args=(app_label, serializer.__class__.__name__),
            kwargs={
                "data": content_data.task_payload,
                "context": self.get_deferred_context(request),
            },
        )
        return OperationPostponedResponse(async_result, request)

    def init_content_data(self, serializer, request):
        """
        Initialize content data which will be passed to a created task.

        Args:
            serializer: A serializer retrieved from request data containing already validated data
            request (rest_framework.request.Request): the current HTTP request being handled
        """
        raise NotImplementedError("Subclasses must implement this method.")


class NoArtifactContentUploadViewSet(ContentUploadViewSet):
    """A ViewSet for uploads that do not require to store an uploaded content as an Artifact."""

    def __init__(self, *args, **kwargs):
        """Set a task's function type that creates a new content using a temporary Artifact."""
        super().__init__(*args, **kwargs)
        self._task_function_type = tasks.base.general_create_from_temp_file

    def init_content_data(self, serializer, request):
        """Initialize a temporary Artifact."""
        shared_resources = []

        task_payload = {k: v for k, v in request.data.items()}
        file_content = task_payload.pop("file", None)
        if file_content:
            # in the upload code path make sure, the artifact exists, and the 'file'
            # parameter is replaced by an Artifact; this Artifact will be afterwards
            # deleted because it serves as a temporary storage for file contents
            artifact = Artifact.init_and_validate(file_content)
            try:
                artifact.save()
            except IntegrityError:
                # if artifact already exists, let's use it
                artifact = Artifact.objects.get(sha256=artifact.sha256)

            task_payload["artifact"] = ArtifactSerializer(
                artifact, context={"request": request}
            ).data["pulp_href"]
            shared_resources.append(artifact)

        return ContentUploadData(shared_resources, task_payload)


class SingleArtifactContentUploadViewSet(ContentUploadViewSet):
    """A ViewSet which can be used to store an uploaded content as an Artifact."""

    def init_content_data(self, serializer, request):
        """Create an Artifact from the uploaded data."""
        artifact = serializer.validated_data["artifact"]

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

        return ContentUploadData([artifact], task_payload)
