import re

from gettext import gettext as _
from drf_yasg.utils import swagger_auto_schema
from drf_yasg.openapi import Parameter
from rest_framework import mixins, serializers
from rest_framework.decorators import detail_route
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
    http_method_names = ['get', 'post', 'head', 'put', 'delete']  # remove PATCH

    content_range_pattern = r'^bytes (\d+)-(\d+)/(\d+|[*])$'
    content_range_parameter = \
        Parameter(name='Content-Range', in_='header', required=True, type='string',
                  pattern=content_range_pattern,
                  description='The Content-Range header specifies the location of the file chunk '
                              'within the file.')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return UploadDetailSerializer
        return UploadSerializer

    @swagger_auto_schema(operation_summary="Upload a file chunk",
                         request_body=UploadChunkSerializer,
                         manual_parameters=[content_range_parameter],
                         responses={200: UploadSerializer})
    def update(self, request, pk=None):
        """
        Upload a chunk for an upload.
        """
        upload = self.get_object()

        try:
            chunk = request.data['file']
        except KeyError:
            raise serializers.ValidationError(_("Missing 'file' parameter."))

        content_range = request.META.get('HTTP_CONTENT_RANGE', '')
        match = re.compile(self.content_range_pattern).match(content_range)
        if not match:
            raise serializers.ValidationError(_("Invalid or missing content range header."))
        start = int(match[1])
        end = int(match[2])

        if (end - start + 1) != len(chunk):
            raise serializers.ValidationError(_("Chunk size does not match content range."))

        if end > upload.size - 1:
            raise serializers.ValidationError(_("End byte is greater than upload size."))

        sha256 = request.data.get('sha256')
        upload.append(chunk, start, sha256)

        serializer = UploadSerializer(upload, context={'request': request})
        return Response(serializer.data)

    @swagger_auto_schema(operation_summary="Finish an Upload",
                         request_body=UploadCommitSerializer,
                         responses={202: AsyncOperationResponseSerializer})
    @detail_route(methods=('post',))
    def commit(self, request, pk):
        """
        Generates a Task to commit the upload and create an artifact
        """
        try:
            sha256 = request.data['sha256']
        except KeyError:
            raise serializers.ValidationError(_("Checksum not supplied."))

        upload = self.get_object()
        async_result = enqueue_with_reservation(
            tasks.upload.commit, [upload],
            args=(upload.pk, sha256),
        )
        return OperationPostponedResponse(async_result, request)
