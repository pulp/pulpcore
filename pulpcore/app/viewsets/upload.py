from drf_yasg.utils import swagger_auto_schema
from drf_yasg.openapi import Parameter
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
    UploadDetailSerializer
)
from pulpcore.app.serializers.upload import CONTENT_RANGE_PATTERN
from pulpcore.app.viewsets import BaseFilterSet
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NamedModelViewSet
from pulpcore.app.viewsets.custom_filters import IsoDateTimeFilter
from pulpcore.tasking.tasks import enqueue_with_reservation


class UploadFilter(BaseFilterSet):
    completed = IsoDateTimeFilter(field_name='completed')

    class Meta:
        model = Upload
        fields = {
            'completed': DATETIME_FILTER_OPTIONS + ['isnull']
        }


class UploadViewSet(NamedModelViewSet,
                    mixins.CreateModelMixin,
                    mixins.RetrieveModelMixin,
                    mixins.UpdateModelMixin,
                    mixins.DestroyModelMixin,
                    mixins.ListModelMixin):
    """View for chunked uploads."""
    endpoint_name = 'uploads'
    queryset = Upload.objects.all()
    filterset_class = UploadFilter
    http_method_names = ['get', 'post', 'head', 'put', 'delete']

    content_range_parameter = \
        Parameter(name='Content-Range', in_='header', required=True, type='string',
                  pattern=CONTENT_RANGE_PATTERN,
                  description='The Content-Range header specifies the location of the file chunk '
                              'within the file.')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UploadDetailSerializer
        if self.action == 'update':
            return UploadChunkSerializer
        if self.action == 'commit':
            return UploadCommitSerializer
        return UploadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.action == 'update' and self.kwargs.get("pk"):
            context["upload"] = self.get_object()
        return context

    @swagger_auto_schema(operation_summary="Upload a file chunk",
                         request_body=UploadChunkSerializer,
                         manual_parameters=[content_range_parameter],
                         responses={200: UploadSerializer})
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

        serializer = UploadSerializer(upload, context={'request': request})
        return Response(serializer.data)

    @swagger_auto_schema(operation_summary="Finish an Upload",
                         request_body=UploadCommitSerializer,
                         responses={202: AsyncOperationResponseSerializer})
    @action(detail=True, methods=['post'])
    def commit(self, request, pk):
        """
        Queues a Task that creates an Artifact, and the Upload gets deleted and cannot be re-used.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sha256 = serializer.validated_data['sha256']

        upload = self.get_object()
        async_result = enqueue_with_reservation(
            tasks.upload.commit, [upload],
            args=(upload.pk, sha256),
        )
        return OperationPostponedResponse(async_result, request)
