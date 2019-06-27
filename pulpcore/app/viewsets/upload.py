import re
from datetime import datetime

from gettext import gettext as _
from drf_yasg.utils import swagger_auto_schema
from drf_yasg.openapi import Parameter
from rest_framework import mixins, serializers
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from pulpcore.app.models import Upload
from pulpcore.app.serializers import UploadChunkSerializer, UploadCommitSerializer, UploadSerializer
from pulpcore.app.viewsets import BaseFilterSet
from pulpcore.app.viewsets.base import DATETIME_FILTER_OPTIONS, NamedModelViewSet
from pulpcore.app.viewsets.custom_filters import IsoDateTimeFilter


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
    serializer_class = UploadSerializer
    filterset_class = UploadFilter
    http_method_names = ['get', 'post', 'head', 'put', 'delete']  # remove PATCH

    content_range_pattern = r'^bytes (\d+)-(\d+)/(\d+|[*])$'
    content_range_parameter = \
        Parameter(name='Content-Range', in_='header', required=True, type='string',
                  pattern=content_range_pattern,
                  description='The Content-Range header specifies the location of the file chunk '
                              'within the file.')

    @swagger_auto_schema(operation_summary="Upload a file chunk",
                         request_body=UploadChunkSerializer,
                         manual_parameters=[content_range_parameter],
                         responses={200: UploadSerializer})
    def update(self, request, pk=None):
        """
        Upload a chunk for an upload.
        """
        upload = self.get_object()

        if upload.completed is not None:
            raise serializers.ValidationError(_("Cannot upload chunk for a completed upload."))

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

        upload.append(chunk, start)

        serializer = UploadSerializer(upload, context={'request': request})
        return Response(serializer.data)

    @swagger_auto_schema(operation_summary="Finish an Upload",
                         request_body=UploadCommitSerializer,
                         responses={200: UploadSerializer})
    @detail_route(methods=('put',))
    def commit(self, request, pk):
        """
        Commit the upload and mark it as completed.
        """
        upload = self.get_object()

        try:
            sha256 = request.data['sha256']
        except KeyError:
            raise serializers.ValidationError(_("Checksum not supplied."))

        if sha256 != upload.sha256:
            raise serializers.ValidationError(_("Checksum does not match upload."))

        if upload.completed is not None:
            raise serializers.ValidationError(_("Upload is already complete."))

        upload.completed = datetime.now()
        upload.save()

        serializer = UploadSerializer(upload, context={'request': request})
        return Response(serializer.data)
