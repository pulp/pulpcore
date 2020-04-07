from import_export import resources
from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import (
    Repository,
)


class QueryModelResource(resources.ModelResource):
    """
    A ModelResource that knows the RepositoryVersion to use to filter its query

    QueryModelResource has-a repository-version that can be used to limit its export, and a
    queryset that is derived from that repository-version.

    A plugin-writer will subclass their ModelResources from QueryModelResource,
    and use it to define the limiting query

    Attributes:

        repo_version (models.RepositoryVersion): The RepositoryVersion whose content we would like
            to export
        queryset (django.db.models.query.QuerySet): filtering queryset for this resource
            (driven by repo_version)
    """
    def __init__(self, repo_version=None):
        self.repo_version = repo_version
        self.queryset = None


#
# Artifact and Repository are different from other import-export entities, in that they are not
# repo-version-specific.
#
class ArtifactResource(QueryModelResource):

    class Meta:
        model = Artifact


class RepositoryResource(QueryModelResource):

    class Meta:
        model = Repository


#
# Content, and ContentArtifact are per-repo-version import/exports, and can
# follow the same pattern as a plugin writer would follow
#
class ContentResource(QueryModelResource):
    def __init__(self, repo_version):
        QueryModelResource.__init__(repo_version)
        self.queryset = repo_version.content

    class Meta:
        model = Content


class ContentArtifactResource(QueryModelResource):
    def __init__(self, repo_version):
        QueryModelResource.__init__(repo_version)
        self.queryset = ContentArtifact.objects.filter(content__in=repo_version.content)

    class Meta:
        model = ContentArtifact
