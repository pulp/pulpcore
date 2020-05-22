import os
import re
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

    output_file_info = serializers.JSONField(
        help_text=_("Dictionary of filename: sha256hash entries for export-output-file(s)"),
        read_only=True,
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

    chunk_size = serializers.CharField(
        help_text=_(
            "Chunk export-tarfile into pieces of chunk_size bytes."
            + "Recognizes units of B/KB/MB/GB/TB."
        ),
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
                    "Number of versions ({}) does not match the number of Repositories ({}) for "
                    + "the owning  Exporter!"
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
                )
            )
        return versions

    @staticmethod
    def _parse_size(size):
        try:
            # based on https://stackoverflow.com/a/42865957/2002471
            units = {"B": 1, "KB": 2 ** 10, "MB": 2 ** 20, "GB": 2 ** 30, "TB": 2 ** 40}
            size = size.upper()
            if not re.match(r" ", size):
                size = re.sub(r"([KMGT]?B)", r" \1", size)
            number, unit = [string.strip() for string in size.split()]
            return int(float(number) * units[unit])
        except ValueError:
            raise serializers.ValidationError(
                _("chunk_size '{}' is not valid (valid units are B/KB/MB/GB/TB)").format(size)
            )

    def validate_chunk_size(self, chunk_size):
        the_size = self._parse_size(chunk_size)
        if the_size <= 0:
            raise serializers.ValidationError(
                _("Chunk size {} is not greater than zero!").format(the_size)
            )
        return the_size

    class Meta:
        model = models.PulpExport
        fields = ExportSerializer.Meta.fields + (
            "full",
            "dry_run",
            "versions",
            "chunk_size",
            "output_file_info",
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


class FilesystemExporterSerializer(ExporterSerializer):
    """
    Base serializer for FilesystemExporters.
    """

    path = serializers.CharField(help_text=_("File system location to export to."))

    class Meta:
        model = models.FilesystemExporter
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
