from drf_chunked_upload.views import ChunkedUploadView
from pulpcore.app.models import Upload
from pulpcore.app.serializers import UploadSerializer


class UploadView(ChunkedUploadView):
    """View for chunked uploads."""
    model = Upload
    serializer_class = UploadSerializer
    queryset = Upload.objects.all()
