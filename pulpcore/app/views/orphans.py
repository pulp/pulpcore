from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer
from pulpcore.app.tasks import orphan_cleanup
from pulpcore.tasking.tasks import dispatch


class OrphansView(APIView):
    @extend_schema(
        description="DEPRECATED! Trigger an asynchronous task that deletes all "
        "orphaned content and artifacts. Use the `POST /pulp/api/v3/orphans/cleanup/` call "
        "instead.",
        summary="Delete orphans",
        responses={202: AsyncOperationResponseSerializer},
    )
    def delete(self, request, format=None):
        """
        Cleans up all the Content and Artifact orphans in the system
        """
        deprecation_logger.warning(
            "The `DELETE /pulp/api/v3/orphans/` call is deprecated. Use"
            "`POST /pulp/api/v3/orphans/cleanup/` instead."
        )

        task = dispatch(orphan_cleanup, [])

        return OperationPostponedResponse(task, request)
