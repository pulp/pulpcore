from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer, RepairSerializer
from pulpcore.app.tasks import repair_all_artifacts
from pulpcore.tasking.tasks import dispatch


class RepairView(APIView):
    @extend_schema(
        description=(
            "Trigger an asynchronous task that checks for missing "
            "or corrupted artifacts, and attempts to redownload them."
        ),
        summary="Repair Artifact Storage",
        request=RepairSerializer,
        responses={202: AsyncOperationResponseSerializer},
    )
    def post(self, request):
        """
        Repair artifacts.
        """
        serializer = RepairSerializer(data=request.data)
        serializer.is_valid()

        verify_checksums = serializer.validated_data["verify_checksums"]

        task = dispatch(repair_all_artifacts, args=[verify_checksums])

        return OperationPostponedResponse(task, request)
