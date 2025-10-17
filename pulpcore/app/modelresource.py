import re

from django.conf import settings
from import_export import fields
from import_export.widgets import ForeignKeyWidget
from logging import getLogger

from pulpcore.app.models.content import (
    Artifact,
    Content,
    ContentArtifact,
)
from pulpcore.app.models.repository import Repository
from pulpcore.app.util import get_domain_pk, get_domain
from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.plugin.importexport import QueryModelResource

log = getLogger(__name__)

domain_artifact_file_regex = re.compile(
    r"^artifact/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
)


#
# Artifact and Repository are different from other import-export entities, in that they are not
# repo-version-specific.
#
class ArtifactResource(QueryModelResource):
    """Resource for import/export of artifacts."""

    def before_import_row(self, row, **kwargs):
        """
        Sets digests to None if they are blank strings.

        Args:
            row (tablib.Dataset row): incoming import-row representing a single Variant.
            kwargs: args passed along from the import() call.

        """
        # IF we're domain-enabled *AND NOT IMPORTING INTO DEFAULT*:
        #   REPLACE "their" domain-id with ours, if there is one.
        #   If not, INSERT "our" domain-id into the path in the right place.
        # Otherwise:
        #   REMOVE their domain-id if there is one.
        # Do this before letting QMR run, since it will replace "their" domain-id with "ours"
        upstream_domain_enabled = re.match(domain_artifact_file_regex, row["file"])
        into_default = "default" == get_domain().name
        domain = str(get_domain_pk())

        if settings.DOMAIN_ENABLED and not into_default:  # Replace "their" domain-id with "ours"
            if upstream_domain_enabled:
                row["file"] = row["file"].replace(row["pulp_domain"], domain)
            else:  # Add in our domain-id to the path
                row["file"] = row["file"].replace("artifact", f"artifact/{domain}")
        else:  # Strip domain-id out of the artifact-file *if there is one there*
            if upstream_domain_enabled:
                row["file"] = row["file"].replace(f'artifact/{row["pulp_domain"]}/', "artifact/")

        super().before_import_row(row, **kwargs)

        # the export converts None to blank strings but sha384 and sha512 have unique constraints
        # that get triggered if they are blank. convert checksums back into None if they are blank.
        for checksum in ALL_KNOWN_CONTENT_CHECKSUMS:
            if row[checksum] == "" or checksum not in settings.ALLOWED_CONTENT_CHECKSUMS:
                del row[checksum]

    def set_up_queryset(self):
        """
        :return: Artifacts for a specific domain
        """
        return Artifact.objects.filter(pulp_domain_id=get_domain_pk())

    class Meta:
        model = Artifact
        exclude = QueryModelResource.Meta.exclude + ("timestamp_of_interest",)
        import_id_fields = (
            "pulp_domain",
            "sha256",
        )


class RepositoryResource(QueryModelResource):

    def set_up_queryset(self):
        """
        :return: Repositories for a specific domain
        """
        return Repository.objects.filter(pulp_domain_id=get_domain_pk())

    class Meta:
        model = Repository
        import_id_fields = (
            "pulp_domain",
            "name",
        )
        exclude = QueryModelResource.Meta.exclude + (
            "content",
            "next_version",
            "repository_ptr",
            "remote",
            "pulp_labels",
        )


class ArtifactDomainForeignKeyWidget(ForeignKeyWidget):
    def get_queryset(self, value, row, *args, **kwargs):
        qs = self.model.objects.filter(sha256=row["artifact"], pulp_domain_id=get_domain_pk())
        return qs

    def render(self, value, obj=None, **kwargs):
        return value.sha256 if value else ""


class ContentArtifactResource(QueryModelResource):
    """
    Handles import/export of the ContentArtifact model

    ContentArtifact is different from other import-export entities because it has no 'natural key'
    other than a pulp_id, which aren't shared across instances. We do some magic to link up
    ContentArtifacts to their matching (already-imported) Content.

    Some plugin-models have sub-repositories. We take advantage of the content-mapping
    machinery to account for those contentartifacts as well.
    """

    artifact = fields.Field(
        column_name="artifact",
        attribute="artifact",
        widget=ArtifactDomainForeignKeyWidget(Artifact, "sha256"),
    )
    linked_content = {}

    def __init__(self, repo_version=None, content_mapping=None):
        self.content_mapping = content_mapping
        if not ContentArtifactResource.linked_content:
            ContentArtifactResource.linked_content = self.fetch_linked_content()
        super().__init__(repo_version)

    def before_import_row(self, row, **kwargs):
        """
        Fixes the content-ptr of an incoming content-artifact row at import time.

        Finds the 'original uuid' of the Content for this row, looks it up as the
        'upstream_id' of imported Content, and then replaces the Content-pk with its
        (new) uuid.

        Args:
            row (tablib.Dataset row): incoming import-row representing a single ContentArtifact.
            kwargs: args passed along from the import() call.

        Returns:
            (tablib.Dataset row): row that now points to the new downstream uuid for its content.
        """
        super().before_import_row(row, **kwargs)

        row["content"] = self.linked_content[row["content"]]

    def set_up_queryset(self):
        content_pks = set(self.repo_version.content.values_list("pk", flat=True))

        if self.content_mapping:
            for content_ids in self.content_mapping.values():
                content_pks |= set(content_ids)

        qs = (
            ContentArtifact.objects.filter(content__in=content_pks)
            .order_by("content", "relative_path")
            .select_related("artifact")
        )
        return qs

    def dehydrate_content(self, content_artifact):
        return str(content_artifact.content_id)

    def fetch_linked_content(self):
        linked_content = {}
        c_qs = Content.objects.filter(
            upstream_id__isnull=False, pulp_domain_id=get_domain_pk()
        ).values("upstream_id", "pulp_id")
        for c in c_qs.iterator():
            linked_content[str(c["upstream_id"])] = str(c["pulp_id"])

        return linked_content

    class Meta:
        model = ContentArtifact
        import_id_fields = (
            "content",
            "relative_path",
        )
        exclude = QueryModelResource.Meta.exclude + ("_artifacts",)
