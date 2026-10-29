from gettext import gettext as _

from django.db import DatabaseError
from django.db.utils import IntegrityError
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from pulpcore.app import tasks
from pulpcore.plugin.models import Artifact, MasterModel, PulpTemporaryFile
from pulpcore.plugin.serializers import (
    ArtifactSerializer,
    AsyncOperationResponseSerializer,
)
from pulpcore.plugin.tasking import dispatch
from pulpcore.plugin.viewsets import (
    ContentViewSet,
    OperationPostponedResponse,
)
from pulpcore.tasking.tasks import using_workdir


def _validate_unversioned_repository(serializer):
    """Ensure the upload targets an unversioned repository."""
    repository = serializer.validated_data.get("repository")
    if repository is None or repository.versioned:
        raise ValidationError(_("This endpoint requires a repository with versioned=False."))


def _upload_sync(view, data, context):
    """
    Create content and add it to an unversioned repository within the request.

    This mirrors tasks.base.general_create without dispatching a task, taking locks or creating a
    CreatedResource. Concurrent uploads to the same relative path may both be added, leaving
    two content units at one path. Concurrent requests using the same chunked upload may fail.

    Downloading a file_url and joining the chunks of an upload happen within the request, so
    large or slow files can hit the API server timeout.
    """
    # A request-less context makes the serializer run its deferred validation in-process.
    context["request"] = None
    serializer = view.get_serializer_class()(data=data, context=context)
    # Deferred validation writes temporary files to the CWD, like it would in a task.
    # No transaction on purpose: RepositoryMembership writes are immediate.
    with using_workdir():
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
    if isinstance(instance, MasterModel):
        instance = instance.cast()

    response_data = view.get_serializer(instance).data
    headers = view.get_success_headers(response_data)
    return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)


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
    def create(self, request, **kwargs):
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
    def create(self, request, **kwargs):
        """Create a content unit."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        context = self.get_deferred_context(request)
        task_payload = {k: v for k, v in request.data.items()}

        if file_content := task_payload.pop("file", None):
            temp_file = PulpTemporaryFile.init_and_validate(file_content)
            temp_file.save()
            context["pulp_temp_file_pk"] = str(temp_file.pk)

        exclusive_resources = [
            item for item in (serializer.validated_data.get(key) for key in ("repository",)) if item
        ]

        app_label = self.queryset.model._meta.app_label
        task = dispatch(
            tasks.base.general_create,
            exclusive_resources=exclusive_resources,
            args=(app_label, serializer.__class__.__name__),
            kwargs={"data": task_payload, "context": context},
        )
        return OperationPostponedResponse(task, request)

    # Untested: no plugin with NoArtifact content supports unversioned repositories yet
    @extend_schema(
        description="Synchronously create content and add it to an unversioned repository.",
    )
    @action(detail=False, methods=["post"])
    def upload_sync(self, request, **kwargs):
        """Create a content unit in an unversioned repository without a task."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_unversioned_repository(serializer)

        context = self.get_deferred_context(request)
        data = {k: v for k, v in request.data.items()}

        if file_content := data.pop("file", None):
            temp_file = PulpTemporaryFile.init_and_validate(file_content)
            temp_file.save()
            context["pulp_temp_file_pk"] = str(temp_file.pk)

        return _upload_sync(self, data, context)


class SingleArtifactContentUploadViewSet(DefaultDeferredContextMixin, ContentViewSet):
    """A ViewSet which can be used to store an uploaded content as an Artifact."""

    @extend_schema(
        description="Trigger an asynchronous task to create content,"
        "optionally create new repository version.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def create(self, request, **kwargs):
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

    @extend_schema(
        description="Synchronously create content and add it to an unversioned repository.",
    )
    @action(detail=False, methods=["post"])
    def upload_sync(self, request, **kwargs):
        """Create a content unit in an unversioned repository without a task."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _validate_unversioned_repository(serializer)

        context = self.get_deferred_context(request)
        data = self.init_content_data(serializer, request)

        return _upload_sync(self, data, context)

    def init_content_data(self, serializer, request):
        """Initialize the reference to an Artifact along with relevant task's payload data."""

        task_payload = {k: v for k, v in request.data.items()}
        if "file" in task_payload:
            # in the upload code path make sure, the artifact exists, and the 'file'
            # parameter is replaced by 'artifact'
            file = task_payload.pop("file")
            artifact = Artifact.init_and_validate(file)
            # if artifact already exists, let's use it
            try:
                artifact = Artifact.objects.get(
                    sha256=artifact.sha256, pulp_domain=request.pulp_domain
                )
                if not artifact.pulp_domain.get_storage().exists(artifact.file.name):
                    # artifact.save will do the "recreate file in file storage"
                    # only if file is set and *dirty*, so we need to reset it here
                    artifact.file = file
                    raise Artifact.DoesNotExist
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
