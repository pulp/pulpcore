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
    def set_up_queryset(self):
        return None

    def __init__(self, repo_version=None):
        self.repo_version = repo_version
        if repo_version:
            self.queryset = self.set_up_queryset()

    class Meta:
        import_id_fields = ('pulp_id',)


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
    def set_up_queryset(self):
        return self.repo_version.content

    class Meta:
        model = Content
        fields = ('pulp_id', 'pulp_type')


class ContentArtifactResource(QueryModelResource):
    def set_up_queryset(self):
        return ContentArtifact.objects.filter(content__in=self.repo_version.content)

    class Meta:
        model = ContentArtifact
