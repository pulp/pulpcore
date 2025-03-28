from gettext import gettext as _

from django.conf import settings
from django.db import models
from django_filters import NumberFilter
from rest_framework import mixins, status
from rest_framework.response import Response

from pulpcore.filters import BaseFilterSet
from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.models import Artifact, Content, PublishedMetadata, SigningService
from pulpcore.app.serializers import (
    ArtifactSerializer,
    MultipleArtifactContentSerializer,
    SigningServiceSerializer,
)
from pulpcore.app.util import get_viewset_for_model
from pulpcore.app.viewsets.base import NamedModelViewSet, LabelsMixin
from pulpcore.app.viewsets.custom_filters import LabelFilter

from .custom_filters import (
    ArtifactRepositoryVersionFilter,
    ContentAddedRepositoryVersionFilter,
    ContentRemovedRepositoryVersionFilter,
    ContentRepositoryVersionFilter,
)


class OrphanedFilter(NumberFilter):
    def filter(self, qs, value):
        if value is not None:
            if value < 0:
                time = settings.ORPHAN_PROTECTION_TIME
            else:
                time = value
            qs = qs.orphaned(int(time))
        return qs


class ArtifactFilter(BaseFilterSet):
    """
    Artifact filter Plugin content filters should:
     - inherit from this class
     - add any plugin-specific filters if needed
     - define its own `Meta` class should:
       - specify plugin content model
       - extend `fields` with plugin-specific ones
    """

    repository_version = ArtifactRepositoryVersionFilter()
    orphaned_for = OrphanedFilter(
        help_text="Minutes Artifacts have been orphaned for. -1 uses ORPHAN_PROTECTION_TIME."
    )

    class Meta:
        model = Artifact
        fields = {
            "md5",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha512",
        }


class ArtifactViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
):
    endpoint_name = "artifacts"
    queryset = Artifact.objects.all()
    serializer_class = ArtifactSerializer
    filterset_class = ArtifactFilter

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["create", "list", "retrieve"],
                "principal": "admin",
                "effect": "allow",
            },
        ],
    }

    # Deleting artifacts is a risky operation and will be removed in a future release.
    # However, for compatibility reasons, it is still possible to execute the DELETE
    # request by overriding the DEFAULT_ACCESS_POLICY.
    def destroy(self, request, pk):
        """
        Remove Artifact only if it is not associated with any Content.
        """
        msg = _(
            "destroy is deprecated. Deleting artifacts is a dangerous operation, "
            "use orphan cleanup instead."
        )
        deprecation_logger.warning(msg)
        try:
            return super().destroy(request, pk)
        except models.ProtectedError:
            msg = _("The Artifact cannot be deleted because it is associated with Content.")
            data = {"detail": msg}
            return Response(data, status=status.HTTP_409_CONFLICT)


class ContentFilter(BaseFilterSet):
    """
    Plugin content filters should:
     - inherit from this class
     - add any plugin-specific filters if needed
     - define its own `Meta` class which should:
       - specify plugin content model
       - extend `fields` with plugin-specific ones

    Allows you to filter the content app by repository version.

    Fields:

        repository_version:
            Return Content which is contained within this repository version.
        repository_version_added:
            Return Content which was added in this repository version.
        repository_version_removed:
            Return Content which was removed from this repository version.
        orphaned_for:
            Return Content which has been orphaned for a given number of minutes;
            -1 uses ORPHAN_PROTECTION_TIME value.
        pulp_label_select:
            Return Content which has has the specified label
    """

    repository_version = ContentRepositoryVersionFilter()
    repository_version_added = ContentAddedRepositoryVersionFilter()
    repository_version_removed = ContentRemovedRepositoryVersionFilter()
    orphaned_for = OrphanedFilter(
        help_text="Minutes Content has been orphaned for. -1 uses ORPHAN_PROTECTION_TIME."
    )
    pulp_label_select = LabelFilter()


class BaseContentViewSet(NamedModelViewSet):
    """
    A base class for any content viewset.

    It ensures that 'content/' is a part of endpoint, sets a default filter class and provides
    a default `scope_queryset` method.
    """

    endpoint_name = "content"
    filterset_class = ContentFilter
    # These are just placeholders, the plugin writer would replace them with the actual
    queryset = Content.objects.all().exclude(pulp_type=PublishedMetadata.get_pulp_type())
    serializer_class = MultipleArtifactContentSerializer

    def get_queryset(self):
        """Apply optimizations for list endpoint."""
        qs = super().get_queryset()
        if getattr(self, "action", "") == "list":
            # Fetch info for artifacts (ContentArtifactsField)
            qs = qs.prefetch_related("contentartifact_set")
        return qs

    def scope_queryset(self, qs):
        """Scope the content based on repositories the user has permission to see."""
        # This has been optimized, see ListRepositoryVersions for more generic version
        repositories = self.queryset.model.repository_types()
        if not self.request.user.is_superuser:
            scoped_repos = []
            for repo in repositories:
                repo_viewset = get_viewset_for_model(repo)()
                setattr(repo_viewset, "request", self.request)
                scoped_repos.extend(repo_viewset.get_queryset().values_list("pk", flat=True))

            # calling the distinct clause at end of the query ensures that no duplicates from
            # joined tables will be returned to the end-user; this behaviour is documented at
            # https://docs.djangoproject.com/en/3.2/topics/db/queries, in the section Spanning
            # multi-valued relationships
            return qs.filter(repositories__in=scoped_repos).distinct()
        return qs


class ListContentViewSet(BaseContentViewSet, mixins.ListModelMixin):
    """Endpoint to list all content."""

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list"],
                "principal": "authenticated",
                "effect": "allow",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        # Even with this role, can only label content user has access to
        "core.content_labeler": ["core.manage_content_labels"],
    }

    @classmethod
    def routable(cls):
        """Do not hide from the routers."""
        return True


class ContentViewSet(
    BaseContentViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    LabelsMixin,
):
    """
    Content viewset that supports POST and GET by default.
    """


class ReadOnlyContentViewSet(
    BaseContentViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin, LabelsMixin
):
    """
    Content viewset that supports only GET by default.
    """


class SigningServiceViewSet(NamedModelViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
    """
    A ViewSet that supports browsing of existing signing services.
    """

    endpoint_name = "signing-services"
    queryset = SigningService.objects.all()
    serializer_class = SigningServiceSerializer
    filterset_fields = ["name"]
