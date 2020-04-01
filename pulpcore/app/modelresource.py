from import_export import resources
from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import (
    Repository,
    RepositoryVersion,
)


class RepositoryResource(resources.ModelResource):

    class Meta:
        model = Repository


class RepositoryVersionResource(resources.ModelResource):

    class Meta:
        model = RepositoryVersion


class ArtifactResource(resources.ModelResource):

    class Meta:
        model = Artifact


class ContentResource(resources.ModelResource):

    class Meta:
        model = Content


class ContentArtifactResource(resources.ModelResource):

    class Meta:
        model = ContentArtifact

