from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import OpenApiParameter
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from pulpcore.app import tasks
from pulpcore.app.models import Upload
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import (
    AsyncOperationResponseSerializer,
    UploadChunkSerializer,
    UploadCommitSerializer,
    UploadSerializer,
    UploadDetailSerializer,
)
from pulpcore.app.viewsets import NamedModelViewSet, RolesMixin
from pulpcore.tasking.tasks import dispatch


class UploadViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    RolesMixin,
):
    """View for chunked uploads."""

    endpoint_name = "uploads"
    queryset = Upload.objects.all()
    http_method_names = ["get", "post", "head", "put", "delete"]
    filterset_fields = {"size": ["exact", "gt", "lt", "range"]}

    content_range_parameter = OpenApiParameter(
        name="Content-Range",
        location=OpenApiParameter.HEADER,
        required=True,
        type=str,
        description="The Content-Range header specifies the location of the file chunk "
        "within the file.",
    )

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
                "condition": "has_model_perms:core.add_upload",
            },
            {
                "action": ["retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.view_upload",
            },
            {
                "action": ["update", "partial_update", "commit"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.change_upload",
            },
            {
                "action": ["destroy"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_obj_perms:core.delete_upload",
            },
            {
                "action": ["list_roles", "add_role", "remove_role"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": ["has_model_or_obj_perms:core.manage_roles_upload"],
            },
        ],
        "creation_hooks": [
            {
                "function": "add_roles_for_object_creator",
                "parameters": {"roles": "core.upload_owner"},
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }

    LOCKED_ROLES = {
        "core.upload_creator": [
            "core.add_upload",
        ],
        "core.upload_owner": [
            "core.view_upload",
            "core.change_upload",
            "core.delete_upload",
            "core.manage_roles_upload",
        ],
        "core.upload_viewer": [
            "core.view_upload",
        ],
    }

    def get_serializer_class(self):
        if self.action == "retrieve":
            return UploadDetailSerializer
        if self.action == "update":
            return UploadChunkSerializer
        if self.action == "commit":
            return UploadCommitSerializer
        return UploadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == "update" and self.kwargs.get("pk"):
            context["upload"] = self.get_object()
        return context

    @extend_schema(
        summary="Upload a file chunk",
        request=UploadChunkSerializer,
        parameters=[content_range_parameter],
        responses={200: UploadSerializer},
    )
    def update(self, request, pk=None):
        """
        Upload a chunk for an upload.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        chunk = serializer.validated_data["file"]
        start = serializer.validated_data["start"]
        sha256 = serializer.validated_data.get("sha256")

        upload = self.get_object()
        upload.append(chunk, start, sha256)

        serializer = UploadSerializer(upload, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="Finish an Upload",
        request=UploadCommitSerializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    @action(detail=True, methods=["post"])
    def commit(self, request, pk):
        """
        Queues a Task that creates an Artifact, and the Upload gets deleted and cannot be re-used.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sha256 = serializer.validated_data["sha256"]

        upload = self.get_object()
        task = dispatch(tasks.upload.commit, exclusive_resources=[upload], args=(upload.pk, sha256))
        return OperationPostponedResponse(task, request)
