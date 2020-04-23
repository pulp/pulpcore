from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import Repository
from pulpcore.plugin.importexport import QueryModelResource


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
        fields = ("pulp_id", "pulp_type")


class ContentArtifactResource(QueryModelResource):
    def set_up_queryset(self):
        return ContentArtifact.objects.filter(content__in=self.repo_version.content)

    class Meta:
        model = ContentArtifact
