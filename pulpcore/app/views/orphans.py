from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

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
        uri = "/api/v3/orphans/cleanup/"
        if settings.DOMAIN_ENABLED:
            uri = f"/{request.pulp_domain.name}{uri}"
        task = dispatch(orphan_cleanup, exclusive_resources=[uri])

        return OperationPostponedResponse(task, request)
