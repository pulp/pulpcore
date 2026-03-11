from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer, DataRepair7272Serializer
from pulpcore.app.tasks.datarepair import repair_7272
from pulpcore.tasking.tasks import dispatch


class DataRepair7272View(APIView):
    @extend_schema(
        description=(
            "Trigger an asynchronous task that repairs repository version content_ids "
            "cache and content count mismatches (Issue #7272). This task fixes two types "
            "of data corruption: 1) Mismatch between RepositoryVersion.content_ids cache "
            "and actual RepositoryContent relationships, and 2) Mismatch between "
            "RepositoryVersionContentDetails count and actual RepositoryContent count."
        ),
        summary="Repair Repository Version Data (Issue #7272)",
        request=DataRepair7272Serializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    def post(self, request):
        """
        Repair repository version data issues (Issue #7272).
        """
        serializer = DataRepair7272Serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dry_run = serializer.validated_data["dry_run"]

        exclusive_resources = [f"pdrn:{request.pulp_domain.pulp_id}:datarepair-7272"]
        task = dispatch(repair_7272, exclusive_resources=exclusive_resources, args=[dry_run])

        return OperationPostponedResponse(task, request)
