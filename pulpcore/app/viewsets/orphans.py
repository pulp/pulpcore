from drf_spectacular.utils import extend_schema
from rest_framework.viewsets import ViewSet

from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer, OrphansCleanupSerializer


class OrphansCleanupViewset(ViewSet):
    serializer_class = OrphansCleanupSerializer

    @extend_schema(
        description="Trigger an asynchronous orphan cleanup operation.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def cleanup(self, request):
        """
        Triggers an asynchronous orphan cleanup operation.
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.dispatch("cleanup")
        return OperationPostponedResponse(task, request)
