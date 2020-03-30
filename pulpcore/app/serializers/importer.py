import os
from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models, settings
from pulpcore.app.serializers import (
    DetailIdentityField,
    ImportIdentityField,
    ModelSerializer,
    RelatedField,
)


class ImporterSerializer(ModelSerializer):
    """Base serializer for Importers."""
    pulp_href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_("Unique name of the Importer."),
        validators=[UniqueValidator(queryset=models.Importer.objects.all())]
    )

    class Meta:
        model = models.Importer
        fields = ModelSerializer.Meta.fields + ('name',)


class ImportSerializer(ModelSerializer):
    """Serializer for Imports."""
    pulp_href = ImportIdentityField()

    task = RelatedField(
        help_text=_('A URI of the Task that ran the Import.'),
        queryset=models.Task.objects.all(),
        view_name='tasks-detail',
    )

    params = serializers.JSONField(
        help_text=_('Any parameters that were used to create the import.'),
    )

    class Meta:
        model = models.Importer
        fields = ModelSerializer.Meta.fields + ('task', 'params')


class PulpImporterSerializer(ImporterSerializer):
    """Serializer for PulpImporters."""
    repo_mapping = serializers.DictField(
        child=serializers.CharField(),
        help_text=_("Mapping of repo names in an export file to the repo names in Pulp. "
                    "For example, if the export has a repo named 'foo' and the repo to "
                    "import content into was 'bar', the mapping would be \"{'foo': 'bar'}\"."),
        required=False
    )

    def create(self, validated_data):
        """
        Save the PulpImporter and handle saving repo mapping.

        Args:
            validated_data (dict): A dict of validated data to create the PulpImporter

        Raises:
            ValidationError: When there's a problem with the repo mapping.

        Returns:
            PulpImporter: the created PulpImporter
        """
        repo_mapping = validated_data.pop("repo_mapping", {})
        importer = super().create(validated_data)
        try:
            importer.repo_mapping = repo_mapping
        except Exception as err:
            importer.delete()
            raise serializers.ValidationError(_("Bad repo mapping: {}").format(err))
        else:
            return importer

    class Meta:
        model = models.PulpImporter
        fields = ImporterSerializer.Meta.fields + ('repo_mapping',)


class PulpImportSerializer(ModelSerializer):
    """Serializer for call to import into Pulp."""
    path = serializers.CharField(
        help_text=_("Path to export that will be imported.")
    )

    def validate_path(self, value):
        """
        Check if path is in ALLOWED_IMPORT_PATHS.

        Args:
            value (str): The user-provided value path to be validated.

        Raises:
            ValidationError: When path is not in the ALLOWED_IMPORT_PATHS setting.

        Returns:
            The validated value.
        """
        for allowed_path in settings.ALLOWED_IMPORT_PATHS:
            user_provided_realpath = os.path.realpath(value)
            if user_provided_realpath.startswith(allowed_path):
                return value
        raise serializers.ValidationError(_("Path '{}' is not an allowed import "
                                            "path").format(value))

    class Meta:
        model = models.Import
        fields = ('path',)
