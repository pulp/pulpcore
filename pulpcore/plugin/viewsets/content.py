from drf_spectacular.utils import extend_schema

from django.db import DatabaseError
from django.db.utils import IntegrityError

from pulpcore.app import tasks
from pulpcore.plugin.serializers import (
    ArtifactSerializer,
    AsyncOperationResponseSerializer,
)
from pulpcore.plugin.models import Artifact, PulpTemporaryFile
from pulpcore.plugin.tasking import dispatch
from pulpcore.plugin.viewsets import (
    ContentViewSet,
    OperationPostponedResponse,
)


class DefaultDeferredContextMixin:
    """A mixin that provides a method for retrieving the default deferred context."""

    def get_deferred_context(self, request):
        """
        Supply context for deferred validation.

        When overwriting this method, it must return a dict, that is JSON serializable by
        and does _not_ contain 'request' as a key.
        """
        return {}


class NoArtifactContentViewSet(DefaultDeferredContextMixin, ContentViewSet):
    """A ViewSet for content creation that does not require a file to be uploaded."""

    @extend_schema(
        description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """Create a content unit."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        exclusive_resources = [
            item for item in (serializer.validated_data.get(key) for key in ("repository",)) if item
        ]

        task = dispatch(
            tasks.base.general_create,
            exclusive_resources=exclusive_resources,
            args=(self.queryset.model._meta.app_label, serializer.__class__.__name__),
            kwargs={
                "data": {k: v for k, v in request.data.items()},
                "context": self.get_deferred_context(request),
            },
        )
        return OperationPostponedResponse(task, request)


class NoArtifactContentUploadViewSet(DefaultDeferredContextMixin, ContentViewSet):
    """A ViewSet for uploads that do not require to store an uploaded content as an Artifact."""

    @extend_schema(
        description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """Create a content unit."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_payload = {k: v for k, v in request.data.items()}

        file_content = task_payload.pop("file", None)
        temp_file = PulpTemporaryFile.init_and_validate(file_content)
        temp_file.save()

        exclusive_resources = [
            item for item in (serializer.validated_data.get(key) for key in ("repository",)) if item
        ]

        app_label = self.queryset.model._meta.app_label
        context = self.get_deferred_context(request)
        context["pulp_temp_file_pk"] = str(temp_file.pk)
        task = dispatch(
            tasks.base.general_create,
            exclusive_resources=exclusive_resources,
            args=(app_label, serializer.__class__.__name__),
            kwargs={"data": task_payload, "context": context},
        )
        return OperationPostponedResponse(task, request)


class SingleArtifactContentUploadViewSet(DefaultDeferredContextMixin, ContentViewSet):
    """A ViewSet which can be used to store an uploaded content as an Artifact."""

    @extend_schema(
        description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request):
        """Create a content unit."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task_payload = self.init_content_data(serializer, request)

        exclusive_resources = [
            item
            for item in (serializer.validated_data.get(key) for key in ("upload", "repository"))
            if item
        ]

        app_label = self.queryset.model._meta.app_label
        task = dispatch(
            tasks.base.general_create,
            exclusive_resources=exclusive_resources,
            args=(app_label, serializer.__class__.__name__),
            kwargs={
                "data": task_payload,
                "context": self.get_deferred_context(request),
            },
        )
        return OperationPostponedResponse(task, request)

    def init_content_data(self, serializer, request):
        """Initialize the reference to an Artifact along with relevant task's payload data."""
        task_payload = {k: v for k, v in request.data.items()}
        if "file" in task_payload:
            # in the upload code path make sure, the artifact exists, and the 'file'
            # parameter is replaced by 'artifact'
            artifact = Artifact.init_and_validate(task_payload.pop("file"))
            # if artifact already exists, let's use it
            try:
                artifact = Artifact.objects.get(
                    sha256=artifact.sha256, pulp_domain=request.pulp_domain
                )
                artifact.touch()
            except (Artifact.DoesNotExist, DatabaseError):
                try:
                    artifact.save()
                except IntegrityError:
                    artifact = Artifact.objects.get(
                        sha256=artifact.sha256, pulp_domain=request.pulp_domain
                    )
                    artifact.touch()

            task_payload["artifact"] = ArtifactSerializer(
                artifact, context={"request": request}
            ).data["pulp_href"]
        elif "artifact" in serializer.validated_data:
            serializer.validated_data["artifact"].touch()
        # In case of a provided upload object, there is no artifact to touch yet.

        return task_payload
