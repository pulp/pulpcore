import os
from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models, settings
from pulpcore.app.serializers import (
    DetailIdentityField,
    DetailRelatedField,
    ExportIdentityField,
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
        validators=[UniqueValidator(queryset=models.BaseDistribution.objects.all())]
    )

    def validate_path(self, value):
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
    Base serializer for Exporters.
    """
    pulp_href = ExportIdentityField()

    task = RelatedField(
        help_text=_('A URI of the task that ran the Export.'),
        queryset=models.Task.objects.all(),
        view_name='tasks-detail',
    )

    exported_resources = ExportedResourcesSerializer(
        help_text=_('Resources that were exported.'),
        many=True,
    )

    params = serializers.JSONField(
        help_text=_('Any additional parameters that were used to create the export.'),
    )

    class Meta:
        model = models.Exporter
        fields = ModelSerializer.Meta.fields + ('task', 'exported_resources', 'params')


class PulpExporterSerializer(ExporterSerializer):
    """
    Serializer for pulp exports.
    """
    path = serializers.CharField(
        help_text=_("File system location for the pulp export.")
    )

    class Meta:
        model = models.PulpExporter
        fields = ExporterSerializer.Meta.fields + ('path',)


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
