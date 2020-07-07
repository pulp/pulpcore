from gettext import gettext as _

from django.db import models
from rest_framework import mixins, status
from rest_framework.response import Response

from pulpcore.app.models import Artifact, Content, SigningService
from pulpcore.app.serializers import (
    ArtifactSerializer,
    MultipleArtifactContentSerializer,
    SigningServiceSerializer,
)
from pulpcore.app.viewsets.base import BaseFilterSet, NamedModelViewSet

from .custom_filters import (
    ArtifactRepositoryVersionFilter,
    ContentAddedRepositoryVersionFilter,
    ContentRemovedRepositoryVersionFilter,
    ContentRepositoryVersionFilter,
)


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

    def destroy(self, request, pk):
        """
        Remove Artifact only if it is not associated with any Content.
        """
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
    """

    repository_version = ContentRepositoryVersionFilter()
    repository_version_added = ContentAddedRepositoryVersionFilter()
    repository_version_removed = ContentRemovedRepositoryVersionFilter()


class BaseContentViewSet(NamedModelViewSet):
    """
    A base class for any content viewset.

    It ensures that 'content/' is a part of endpoint. It also sets a default filter class.
    """

    endpoint_name = "content"
    filterset_class = ContentFilter
    # These are just placeholders, the plugin writer would replace them with the actual
    queryset = Content.objects.all()
    serializer_class = MultipleArtifactContentSerializer


class ContentViewSet(
    BaseContentViewSet, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin
):
    """
    Content viewset that supports POST and GET by default.
    """


class ReadOnlyContentViewSet(BaseContentViewSet, mixins.RetrieveModelMixin, mixins.ListModelMixin):
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
