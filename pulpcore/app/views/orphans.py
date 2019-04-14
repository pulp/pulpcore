from drf_yasg.utils import swagger_auto_schema
from rest_framework.views import APIView

from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer
from pulpcore.app.tasks import orphan_cleanup
from pulpcore.tasking.tasks import enqueue_with_reservation


class OrphansView(APIView):

    @swagger_auto_schema(operation_description="Trigger an asynchronous task that deletes all"
                                               "orphaned content and artifacts.",
                         operation_summary="Delete orphans",
                         responses={202: AsyncOperationResponseSerializer})
    def delete(self, request, format=None):
        """
        Cleans up all the Content and Artifact orphans in the system
        """
        async_result = enqueue_with_reservation(orphan_cleanup, [])

        return OperationPostponedResponse(async_result, request)
