import os
from gettext import gettext as _

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models, settings
from pulpcore.app.serializers import (
    DetailIdentityField,
    ImportIdentityField,
    ModelSerializer,
    RelatedField,
    ValidateFieldsMixin,
)


class ImporterSerializer(ModelSerializer):
    """Base serializer for Importers."""

    pulp_href = DetailIdentityField(view_name_pattern=r"importer(-.*/.*)-detail")
    name = serializers.CharField(
        help_text=_("Unique name of the Importer."),
        validators=[UniqueValidator(queryset=models.Importer.objects.all())],
    )

    class Meta:
        model = models.Importer
        fields = ModelSerializer.Meta.fields + ("name",)


class ImportSerializer(ModelSerializer):
    """Serializer for Imports."""

    pulp_href = ImportIdentityField()

    task = RelatedField(
        help_text=_("A URI of the Task that ran the Import."),
        queryset=models.Task.objects.all(),
        view_name="tasks-detail",
    )

    params = serializers.JSONField(
        help_text=_("Any parameters that were used to create the import."),
    )

    class Meta:
        model = models.Importer
        fields = ModelSerializer.Meta.fields + ("task", "params")


class PulpImporterSerializer(ImporterSerializer):
    """Serializer for PulpImporters."""

    repo_mapping = serializers.DictField(
        child=serializers.CharField(),
        help_text=_(
            "Mapping of repo names in an export file to the repo names in Pulp. "
            "For example, if the export has a repo named 'foo' and the repo to "
            "import content into was 'bar', the mapping would be \"{'foo': 'bar'}\"."
        ),
        required=False,
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
        except ObjectDoesNotExist as err:
            importer.delete()
            raise serializers.ValidationError(
                _("Failed to find repositories from repo_mapping: {}").format(err)
            )
        else:
            return importer

    class Meta:
        model = models.PulpImporter
        fields = ImporterSerializer.Meta.fields + ("repo_mapping",)


class PulpImportSerializer(ModelSerializer):
    """Serializer for call to import into Pulp."""

    path = serializers.CharField(
        help_text=_("Path to export that will be imported."), required=False
    )
    toc = serializers.CharField(
        help_text=_(
            "Path to a table-of-contents file describing chunks to be validated, "
            + "reassembled, and imported."
        ),
        required=False,
    )
    create_repositories = serializers.BooleanField(
        help_text=_(
            "If True, missing repositories will be automatically created during the import."
        ),
        required=False,
        default=False,
    )

    def _check_path_allowed(self, param, a_path):
        user_provided_realpath = os.path.realpath(a_path)
        for allowed_path in settings.ALLOWED_IMPORT_PATHS:
            if user_provided_realpath.startswith(allowed_path):
                return user_provided_realpath

        raise serializers.ValidationError(
            _("{} '{}' is not an allowed import path").format(param, a_path)
        )

    def validate_path(self, value):
        """
        Check if path exists and is in ALLOWED_IMPORT_PATHS.

        Args:
            value (str): The user-provided value path to be validated.

        Raises:
            ValidationError: When path is not in the ALLOWED_IMPORT_PATHS setting.

        Returns:
            The validated value.
        """
        return self._check_path_allowed("path", value)

    def validate_toc(self, value):
        """
        Check validity of provided 'toc' parameter.

        'toc' must be within ALLOWED_IMPORT_PATHS.

        NOTE: this method does NOT validate existence/sanity of export-files. That
        happens asynchronously, due to time/responsiveness constraints.

        Args:
            value (str): The user-provided toc-file-path to be validated.

        Raises:
            ValidationError: When toc is not in the ALLOWED_IMPORT_PATHS setting

        Returns:
            The validated value.
        """

        return self._check_path_allowed("toc", value)

    def validate(self, data):
        # only one-of 'path'/'toc'
        if data.get("path", None) and data.get("toc", None):
            raise serializers.ValidationError(_("Only one of 'path' and 'toc' may be specified."))

        # requires one-of 'path'/'toc'
        if not data.get("path", None) and not data.get("toc", None):
            raise serializers.ValidationError(_("One of 'path' or 'toc' must be specified."))

        if importer := self.context.get("importer"):
            if importer.repo_mapping and data.get("create_repositories"):
                raise serializers.ValidationError(
                    _("The option 'create_repositories' is not compatible with 'repo_mapping'.")
                )

        return super().validate(data)

    class Meta:
        model = models.Import
        fields = (
            "path",
            "toc",
            "create_repositories",
        )


class EvaluationSerializer(serializers.Serializer):
    """
    Results from evaluating a proposed parameter to a PulpImport call.
    """

    context = serializers.CharField(
        help_text=_("Parameter value being evaluated."),
    )
    is_valid = serializers.BooleanField(
        help_text=_("True if evaluation passed, false otherwise."),
    )
    messages = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("Messages describing results of all evaluations done. May be an empty list."),
    )


class PulpImportCheckResponseSerializer(serializers.Serializer):
    """
    Return the response to a PulpImport import-check call.
    """

    toc = EvaluationSerializer(
        help_text=_("Evaluation of proposed 'toc' file for PulpImport"),
        required=False,
    )
    path = EvaluationSerializer(
        help_text=_("Evaluation of proposed 'path' file for PulpImport"),
        required=False,
    )
    repo_mapping = EvaluationSerializer(
        help_text=_("Evaluation of proposed 'repo_mapping' file for PulpImport"),
        required=False,
    )


class PulpImportCheckSerializer(ValidateFieldsMixin, serializers.Serializer):
    """
    Check validity of provided import-options.

    Provides the ability to check that an import is 'sane' without having to actually
    create an importer.
    """

    path = serializers.CharField(
        help_text=_("Path to export-tar-gz that will be imported."), required=False
    )
    toc = serializers.CharField(
        help_text=_(
            "Path to a table-of-contents file describing chunks to be validated, "
            "reassembled, and imported."
        ),
        required=False,
    )
    repo_mapping = serializers.CharField(
        help_text=_(
            "Mapping of repo names in an export file to the repo names in Pulp. "
            "For example, if the export has a repo named 'foo' and the repo to "
            "import content into was 'bar', the mapping would be \"{'foo': 'bar'}\"."
        ),
        required=False,
    )

    def validate(self, data):
        data = super().validate(data)
        if "path" not in data and "toc" not in data and "repo_mapping" not in data:
            raise serializers.ValidationError(
                _("One of 'path', 'toc', or 'repo_mapping' must be specified.")
            )
        else:
            return data
