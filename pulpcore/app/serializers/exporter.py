import os
from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models, settings
from pulpcore.app.serializers import (
    DetailIdentityField,
    DetailRelatedField,
    ExportIdentityField,
    ExportRelatedField,
    ModelSerializer,
    RelatedField,
    RepositoryVersionRelatedField,
)

from pulpcore.app.util import get_viewset_for_model


class ExporterSerializer(ModelSerializer):
    """
    Base serializer for Exporters.
    """

    pulp_href = DetailIdentityField(view_name_pattern=r"exporter(-.*/.*)-detail",)
    name = serializers.CharField(
        help_text=_("Unique name of the file system exporter."),
        validators=[UniqueValidator(queryset=models.Exporter.objects.all())],
    )

    @staticmethod
    def validate_path(value, check_is_dir=False):
        """
        Check if path is in ALLOWED_EXPORT_PATHS.

        Args:
            value: The user-provided value path to be validated.
            check_is_dir: If true, insure path ends with a directory

        Raises:
            ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting.

        Returns:
            The validated value.
        """
        for allowed_path in settings.ALLOWED_EXPORT_PATHS:
            user_provided_realpath = os.path.realpath(value)
            if user_provided_realpath.startswith(allowed_path):
                if check_is_dir:  # fail if exists and not-directory
                    if os.path.exists(user_provided_realpath) and not os.path.isdir(
                        user_provided_realpath
                    ):
                        raise serializers.ValidationError(
                            _("Path '{}' must be a directory " "path").format(value)
                        )
                return value
        raise serializers.ValidationError(
            _("Path '{}' is not an allowed export " "path").format(value)
        )

    class Meta:
        model = models.Exporter
        fields = ModelSerializer.Meta.fields + ("name",)


class ExportedResourcesSerializer(ModelSerializer):
    def to_representation(self, data):
        viewset = get_viewset_for_model(data.content_object)
        serializer = viewset.serializer_class(data.content_object, context={"request": None})
        return serializer.data.get("pulp_href")

    class Meta:
        model = models.ExportedResource
        fields = []


class ExportSerializer(ModelSerializer):
    """
    Base serializer for Exports.
    """

    pulp_href = ExportIdentityField()

    task = RelatedField(
        help_text=_("A URI of the task that ran the Export."),
        queryset=models.Task.objects.all(),
        view_name="tasks-detail",
        required=False,
        allow_null=True,
    )

    exported_resources = ExportedResourcesSerializer(
        help_text=_("Resources that were exported."), read_only=True, many=True,
    )

    params = serializers.JSONField(
        help_text=_("Any additional parameters that were used to create the export."),
        read_only=True,
    )

    class Meta:
        model = models.Export
        fields = ModelSerializer.Meta.fields + ("task", "exported_resources", "params")


class PulpExportSerializer(ExportSerializer):
    """
    Serializer for PulpExports.
    """

    sha256 = serializers.CharField(
        help_text=_("The SHA-256 checksum of the exported .tar.gz."), read_only=True,
    )

    filename = serializers.CharField(
        help_text=_("The full-path filename of the exported .tar.gz."), read_only=True,
    )

    dry_run = serializers.BooleanField(
        help_text=_("Generate report on what would be exported and disk-space required."),
        default=False,
        required=False,
        write_only=True,
    )
    full = serializers.BooleanField(
        help_text=_("Do a Full (true) or Incremental (false) export."),
        default=True,
        required=False,
        write_only=True,
    )
    versions = RepositoryVersionRelatedField(
        help_text=_("List of explicit repo-version hrefs to export"),
        many=True,
        required=False,
        write_only=True,
    )

    def validate_versions(self, versions):
        """
        If specifying repo-versions explicitly, must provide a version for each exporter-repository
        """
        # make sure counts match
        the_exporter = self.context.get("exporter", None)
        num_repos = the_exporter.repositories.count()
        if num_repos != len(versions):
            raise serializers.ValidationError(
                _(
                    "Number of versions does not match the number of Repositories for the owning "
                    + "Exporter!"
                ).format(num_repos, len(versions))
            )

        # make sure the specified versions 'belong to' the exporter.repositories
        exporter_repos = set(the_exporter.repositories.all())
        version_repos = set([vers.repository for vers in versions])
        if exporter_repos != version_repos:
            raise serializers.ValidationError(
                _(
                    "Requested RepositoryVersions must belong to the Repositories named by the "
                    + "Exporter!"
                ).format(exporter_repos, version_repos)
            )
        return versions

    class Meta:
        model = models.PulpExport
        fields = ExportSerializer.Meta.fields + (
            "sha256",
            "filename",
            "full",
            "dry_run",
            "versions",
        )


class PulpExporterSerializer(ExporterSerializer):
    """
    Serializer for pulp exporters.
    """

    path = serializers.CharField(help_text=_("File system directory to store exported tar.gzs."))

    repositories = DetailRelatedField(
        view_name_pattern=r"repositories(-.*/.*)-detail",
        queryset=models.Repository.objects.all(),
        many=True,
    )
    last_export = ExportRelatedField(
        help_text=_("Last attempted export for this PulpExporter"),
        queryset=models.PulpExport.objects.all(),
        many=False,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = models.PulpExporter
        fields = ExporterSerializer.Meta.fields + ("path", "repositories", "last_export")


class FileSystemExporterSerializer(ExporterSerializer):
    """
    Base serializer for FileSystemExporters.
    """

    path = serializers.CharField(help_text=_("File system location to export to."))

    class Meta:
        model = models.FileSystemExporter
        fields = ExporterSerializer.Meta.fields + ("path",)


class PublicationExportSerializer(serializers.Serializer):
    """
    Serializer for exporting publications.
    """

    publication = DetailRelatedField(
        required=True,
        help_text=_("A URI of the publication to be exported."),
        view_name_pattern=r"publications(-.*/.*)-detail",
        queryset=models.Publication.objects.all(),
    )
