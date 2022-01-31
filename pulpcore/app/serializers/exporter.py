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
    RelatedResourceField,
    RepositoryVersionRelatedField,
)
from pulpcore.constants import FS_EXPORT_CHOICES, FS_EXPORT_METHODS


class ExporterSerializer(ModelSerializer):
    """
    Base serializer for Exporters.
    """

    pulp_href = DetailIdentityField(view_name_pattern=r"exporter(-.*/.*)-detail")
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
                            _("Path '{}' must be a directory path").format(value)
                        )
                return value
        raise serializers.ValidationError(
            _("Path '{}' is not an allowed export path").format(value)
        )

    class Meta:
        model = models.Exporter
        fields = ModelSerializer.Meta.fields + ("name",)


class ExportedResourceField(RelatedResourceField):
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

    exported_resources = ExportedResourceField(
        help_text=_("Resources that were exported."),
        many=True,
        read_only=True,
        view_name="None",  # This is a polymorphic field. The serializer does not need a view name.
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

    toc_info = serializers.JSONField(
        help_text=_("Filename and sha256-checksum of table-of-contents for this export"),
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
        help_text=_("List of explicit repo-version hrefs to export (replaces current_version)."),
        many=True,
        required=False,
        write_only=True,
    )

    MAX_CHUNK_BYTES = 1024 * 1024 * 1024 * 1024  # 1 TB
    chunk_size = serializers.CharField(
        help_text=_(
            "Chunk export-tarfile into pieces of chunk_size bytes. "
            + "Recognizes units of B/KB/MB/GB/TB. A chunk has a maximum "
            + "size of 1TB."
        ),
        required=False,
        write_only=True,
    )

    start_versions = RepositoryVersionRelatedField(
        help_text=_("List of explicit last-exported-repo-version hrefs (replaces last_export)."),
        many=True,
        required=False,
        write_only=True,
    )

    def _validate_versions_to_repos(self, the_versions):
        """
        If specifying repo-versions explicitly, must provide a version for each exporter-repository
        """
        # make sure counts match
        the_exporter = self.context.get("exporter", None)
        num_repos = the_exporter.repositories.count()
        if num_repos != len(the_versions):
            raise serializers.ValidationError(
                _(
                    "Number of versions ({}) does not match the number of Repositories ({}) for "
                    + "the owning  Exporter!"
                ).format(num_repos, len(the_versions))
            )

        # make sure the specified versions 'belong to' the exporter.repositories
        exporter_repos = set(the_exporter.repositories.all())
        version_repos = set([vers.repository for vers in the_versions])
        if exporter_repos != version_repos:
            raise serializers.ValidationError(
                _(
                    "Requested RepositoryVersions must belong to the Repositories named by the "
                    + "Exporter!"
                )
            )
        return the_versions

    def validate_versions(self, versions):
        return self._validate_versions_to_repos(versions)

    def validate_start_versions(self, start_versions):
        return self._validate_versions_to_repos(start_versions)

    def validate(self, data):
        # If we requested start_versions, make sure we did not forget to specify full=False
        if data.get("start_versions", None) and data.get("full", True):
            raise serializers.ValidationError(
                _("start_versions is only valid for incremental exports (full=False)")
            )

        # If we requested full=False, make sure we either specified start_versions= or
        # have a previous-export for our Exporter.
        if not data.get("full", True):
            the_exporter = self.context.get("exporter", None)
            if not data.get("start_versions", None) and not the_exporter.last_export:
                raise serializers.ValidationError(
                    _(
                        "Incremental export can only be requested when there is a previous export "
                        + "or start_versions= has been specified."
                    )
                )
        return super().validate(data)

    @staticmethod
    def _parse_size(size):
        try:
            # based on https://stackoverflow.com/a/42865957/2002471
            units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40}
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
        if the_size > self.MAX_CHUNK_BYTES:
            raise serializers.ValidationError(
                _("Chunk size in bytes {} is greater than max-chunk-size {}!").format(
                    the_size, self.MAX_CHUNK_BYTES
                )
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
            "start_versions",
            "toc_info",
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


class FilesystemExportSerializer(ExportSerializer):
    """
    Serializer for FilesystemExports.
    """

    publication = DetailRelatedField(
        required=False,
        help_text=_("A URI of the publication to be exported."),
        view_name_pattern=r"publications(-.*/.*)-detail",
        queryset=models.Publication.objects.all(),
        write_only=True,
    )

    repository_version = RepositoryVersionRelatedField(
        help_text=_("A URI of the repository version export."),
        required=False,
        write_only=True,
    )

    def validate(self, data):
        if ("publication" not in data and "repository_version" not in data) or (
            "publication" in data and "repository_version" in data
        ):
            raise serializers.ValidationError(
                _("publication or repository_version must either be supplied but not both.")
            )
        return data

    class Meta:
        model = models.FilesystemExport
        fields = ExportSerializer.Meta.fields + ("publication", "repository_version")


class FilesystemExporterSerializer(ExporterSerializer):
    """
    Serializer for FilesystemExporters.
    """

    path = serializers.CharField(help_text=_("File system location to export to."))

    method = serializers.ChoiceField(
        help_text=_("Method of exporting"),
        choices=(FS_EXPORT_CHOICES),
        default=FS_EXPORT_METHODS.WRITE,
    )

    class Meta:
        model = models.FilesystemExporter
        fields = ExporterSerializer.Meta.fields + ("path", "method")
