from drf_spectacular.utils import extend_schema
from rest_framework.viewsets import ViewSet

from pulpcore.app.response import OperationPostponedResponse
from pulpcore.app.serializers import AsyncOperationResponseSerializer, ReclaimSpaceSerializer
from pulpcore.app.tasks import reclaim_space
from pulpcore.tasking.tasks import dispatch


class ReclaimSpaceViewSet(ViewSet):
    """
    Viewset for reclaim disk space endpoint.
    """

    serializer_class = ReclaimSpaceSerializer

    @extend_schema(
        description="Trigger an asynchronous space reclaim operation.",
        responses={202: AsyncOperationResponseSerializer},
    )
    def reclaim(self, request):
        """
        Triggers an asynchronous space reclaim operation.
        """
        serializer = ReclaimSpaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        repos = serializer.validated_data.get("repo_hrefs", [])
        keeplist = serializer.validated_data.get("repo_versions_keeplist", [])
        reclaim_repo_pks = []
        keeplist_rv_pks = []
        for repo in repos:
            reclaim_repo_pks.append(repo.pk)
        for rv in keeplist:
            repos.append(rv.repository)
            keeplist_rv_pks.append(rv.pk)

        task = dispatch(
            reclaim_space,
            shared_resources=repos,
            kwargs={
                "repo_pks": reclaim_repo_pks,
                "keeplist_rv_pks": keeplist_rv_pks,
            },
        )

        return OperationPostponedResponse(task, request)
