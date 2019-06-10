from drf_chunked_upload.views import ChunkedUploadView
from pulpcore.app.models import Upload
from pulpcore.app.serializers import (
    UploadSerializer,
    UploadFinishSerializer,
    UploadPOSTSerializer,
    UploadPUTSerializer,
)
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin
from rest_framework.viewsets import GenericViewSet
from rest_framework.parsers import FormParser, MultiPartParser

from drf_yasg.utils import swagger_auto_schema
from drf_yasg.openapi import Parameter


class UploadViewSet(GenericViewSet, ChunkedUploadView, CreateModelMixin, DestroyModelMixin):
    """View for chunked uploads."""

    model = Upload
    serializer_class = UploadSerializer
    queryset = Upload.objects.all()
    parser_classes = (MultiPartParser, FormParser)

    content_range_parameter = Parameter(
        name="Content-Range",
        in_="header",
        required=True,
        type="string",
        pattern=r"^bytes (\d+)-(\d+)\/(\d+)$",
        description="The Content-Range header specifies the location of the file chunk "
        "within the file.",
    )

    @swagger_auto_schema(
        operation_summary="Start an Upload",
        operation_id="uploads_create",
        request_body=UploadPUTSerializer,
        manual_parameters=[content_range_parameter],
        responses={200: UploadSerializer},
    )
    def put_create(self, *args, **kwargs):
        """
        Start a chunked upload by uploading the first chunk.
        """
        return super().put(*args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Continue an Upload",
        operation_id="uploads_update",
        request_body=UploadPUTSerializer,
        manual_parameters=[content_range_parameter],
        responses={200: UploadSerializer},
    )
    def put_update(self, *args, **kwargs):
        """
        Continue the upload by uploading the next file chunk.
        """
        return super().put(*args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Finish an Upload",
        operation_id="uploads_finish",
        request_body=UploadFinishSerializer,
        responses={200: UploadSerializer},
    )
    def post(self, *args, **kwargs):
        """
        Mark the Upload as "complete".

        The md5 checksum is used to validate the integrity of the upload.
        """
        return super().post(*args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create an Upload",
        operation_id="uploads_create_and_check",
        request_body=UploadPOSTSerializer,
        responses={200: UploadSerializer},
    )
    def post_create(self, *args, **kwargs):
        """
        Create an upload from a entire file as one chunk.
        """
        return super().post(*args, **kwargs)

    def list(self, *args, **kwargs):
        """
        List all the uploads.
        """
        return super().list(*args, **kwargs)

    def get_serializer_class(self):
        """
        Returns the serializer needed for performing the requested action.
        """
        if self.action == "post_create":
            return UploadPOSTSerializer
        if self.action == "put_create":
            return UploadPUTSerializer
        return UploadSerializer
