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
)

from pulpcore.app.util import get_viewset_for_model


class ExporterSerializer(ModelSerializer):
    """
    Base serializer for Exporters.
    """
    pulp_href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_("Unique name of the file system exporter."),
        validators=[UniqueValidator(queryset=models.Exporter.objects.all())]
    )

    @staticmethod
    def validate_path(value, check_is_dir=False):
        """
        Check if path is in ALLOWED_EXPORT_PATHS.

        Args:
            value: The user-provided value path to be validated.

        Raises:
            ValidationError: When path is not in the ALLOWED_EXPORT_PATHS setting.

        Returns:
            The validated value.
        """
        for allowed_path in settings.ALLOWED_EXPORT_PATHS:
            user_provided_realpath = os.path.realpath(value)
            if user_provided_realpath.startswith(allowed_path):
                if check_is_dir:  # fail if exists and not-directory
                    if os.path.exists(user_provided_realpath) \
                            and not os.path.isdir(user_provided_realpath):
                        raise serializers.ValidationError(_("Path '{}' must be a directory "
                                                            "path").format(value))
                return value
        raise serializers.ValidationError(_("Path '{}' is not an allowed export "
                                            "path").format(value))

    class Meta:
        model = models.Exporter
        fields = ModelSerializer.Meta.fields + ('name',)


class ExportedResourcesSerializer(ModelSerializer):

    def to_representation(self, data):
        viewset = get_viewset_for_model(data.content_object)
        serializer = viewset.serializer_class(data.content_object, context={'request': None})
        return serializer.data.get('pulp_href')

    class Meta:
        model = models.ExportedResource
        fields = []


class ExportSerializer(ModelSerializer):
    """
    Base serializer for Exports.
    """
    pulp_href = ExportIdentityField()

    task = RelatedField(
        help_text=_('A URI of the task that ran the Export.'),
        queryset=models.Task.objects.all(),
        view_name='tasks-detail',
    )

    exported_resources = ExportedResourcesSerializer(
        help_text=_('Resources that were exported.'),
        read_only=True,
        many=True,
    )

    params = serializers.JSONField(
        help_text=_('Any additional parameters that were used to create the export.'),
    )

    class Meta:
        model = models.Export
        fields = ModelSerializer.Meta.fields + ('task', 'exported_resources', 'params')


class PulpExportSerializer(ExportSerializer):
    """
    Serializer for PulpExports.
    """
    sha256 = serializers.CharField(
        help_text=_("The SHA-256 checksum of the exported .tar.gz."),
        required=False,
        allow_null=True,
    )

    filename = serializers.CharField(
        help_text=_("The full-path filename of the exported .tar.gz."),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = models.PulpExport
        fields = ExportSerializer.Meta.fields + ('sha256', 'filename', )


class PulpExporterSerializer(ExporterSerializer):
    """
    Serializer for pulp exporters.
    """
    path = serializers.CharField(
        help_text=_("File system directory to store exported tar.gzs.")
    )

    repositories = serializers.PrimaryKeyRelatedField(queryset=models.Repository.objects.all(),
                                                      many=True)
    last_export = ExportRelatedField(
        help_text=_("Last attempted export for this PulpExporter"),
        queryset=models.PulpExport.objects.all(),
        many=False,
        required=False,
    )

    class Meta:
        model = models.PulpExporter
        fields = ExporterSerializer.Meta.fields + ('path', 'repositories', 'last_export')


class FileSystemExporterSerializer(ExporterSerializer):
    """
    Base serializer for FileSystemExporters.
    """
    path = serializers.CharField(
        help_text=_("File system location to export to.")
    )

    class Meta:
        model = models.FileSystemExporter
        fields = ExporterSerializer.Meta.fields + ('path',)


class PublicationExportSerializer(serializers.Serializer):
    """
    Serializer for exporting publications.
    """
    publication = DetailRelatedField(
        required=True,
        help_text=_('A URI of the publication to be exported.'),
        queryset=models.Publication.objects.all(),
    )
