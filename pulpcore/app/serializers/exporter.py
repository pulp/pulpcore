from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models
from pulpcore.app.serializers import (
    DetailIdentityField,
    DetailRelatedField,
    ModelSerializer,
)


class FileSystemExporterSerializer(ModelSerializer):
    """
    Base serializer for FileSystemExporters.
    """
    pulp_href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_("Unique name of the file system exporter."),
        validators=[UniqueValidator(queryset=models.BaseDistribution.objects.all())]
    )
    path = serializers.CharField(
        help_text=_("File system location to export to.")
    )

    class Meta:
        model = models.FileSystemExporter
        fields = ModelSerializer.Meta.fields + (
            'path',
            'name',
        )


class PublicationExportSerializer(serializers.Serializer):
    """
    Serializer for exporting publications.
    """
    publication = DetailRelatedField(
        required=True,
        help_text=_('A URI of the publication to be exported.'),
        queryset=models.Publication.objects.all(),
    )
