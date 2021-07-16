import json

from gettext import gettext as _

from django.db import IntegrityError, transaction

from rest_framework import serializers
from rest_framework.exceptions import ValidationError as DRFValidationError

from pulpcore.app import models
from pulpcore.app.serializers import (
    DetailIdentityField,
    DetailRelatedField,
    ModelSerializer,
)
from pulpcore.tasking.util import get_url


class AlternateContentSourcePathField(serializers.JSONField):
    """Serializer field for AlternateContentSource."""

    def to_representation(self, acs_pk):
        """
        A serializer field for AlternateContentSourcePath models.

        Args:
            acs_pk (pk of AlternateContentSource instance): UUID of AlternateContentSource

        Returns:
            A list of paths related to AlternateContentSource
        """
        return [
            acs_path.path
            for acs_path in models.AlternateContentSourcePath.objects.filter(
                alternate_content_source=acs_pk
            )
        ]

    def to_internal_value(self, data):
        try:
            paths = json.loads(data)
        except json.JSONDecodeError:
            raise DRFValidationError(_("Paths must be a list."))
        return paths


class AlternateContentSourceSerializer(ModelSerializer):
    """
    Serializer for the AlternateContentSource.
    """

    pulp_href = DetailIdentityField(view_name_pattern=r"acs(-.*/.*)-detail")
    name = serializers.CharField(help_text=_("Name of Alternate Content Source."), required=True)
    last_refreshed = serializers.DateTimeField(
        help_text=_("Date of last refresh of AlternateContentSource."),
        allow_null=True,
        required=False,
    )
    remote = DetailRelatedField(
        help_text=_("The remote to provide alternate content source."),
        view_name_pattern=r"remotes(-.*/.*)-detail",
        queryset=models.Remote.objects.all(),
        required=True,
    )
    paths = AlternateContentSourcePathField(required=False, source="pk")

    def validate_remote(self, remote):
        if remote.policy != "on_demand":
            raise serializers.ValidationError(
                _("Remote used with alternate content source must have the 'on_demand' policy.")
            )
        return remote

    def create(self, validated_data):
        """Create Alternate Content Source and its path if specified."""
        paths = validated_data.pop("pk", [])
        try:
            acs = super().create(validated_data)
        except IntegrityError:
            raise DRFValidationError(
                _(
                    'Alternate Content Source with name "{}" already exists.'.format(
                        validated_data.get("name")
                    )
                )
            )
        try:
            with transaction.atomic():
                self._update_paths(acs, paths)
        except DRFValidationError as exc:
            acs.delete()
            raise exc
        return acs

    def _update_paths(self, acs, paths):
        """Update Alternate Content Source paths."""
        all_paths = [
            acs_path.path
            for acs_path in models.AlternateContentSourcePath.objects.filter(
                alternate_content_source=acs.pk
            )
        ]
        existing_paths = [
            acs_path.path
            for acs_path in models.AlternateContentSourcePath.objects.filter(
                path__in=paths, alternate_content_source=acs.pk
            )
        ]
        to_remove = [path for path in all_paths if path not in existing_paths if path not in paths]
        to_add = [path for path in paths if path not in existing_paths]

        if to_remove:
            for acs_path in models.AlternateContentSourcePath.objects.filter(path__in=to_remove):
                acs_path.delete()
        if to_add:
            for acs_path in to_add:
                new_path = {
                    "alternate_content_source": get_url(acs),
                    "path": acs_path,
                }
                acs_path_serializer = AlternateContentSourcePathSerializer(data=new_path)
                acs_path_serializer.is_valid(raise_exception=True)
                acs_path_serializer.save()

        # if no paths for an ACS, we need create empty path to use base path of ACS remote
        if not models.AlternateContentSourcePath.objects.filter(alternate_content_source=acs.pk):
            empty_path_serializer_data = {"alternate_content_source": get_url(acs), "path": ""}
            empty_path_serializer = AlternateContentSourcePathSerializer(
                data=empty_path_serializer_data
            )
            empty_path_serializer.is_valid(raise_exception=True)
            empty_path_serializer.save()

    def update(self, instance, validated_data):
        """Update an Alternate Content Source."""
        instance.name = validated_data.get("name", instance.name)
        instance.remote = validated_data.get("remote", instance.remote)
        paths = validated_data.pop("pk", [])
        with transaction.atomic():
            self._update_paths(instance, paths)
            instance.save()
        return instance

    class Meta:
        model = models.AlternateContentSource
        fields = ModelSerializer.Meta.fields + (
            "pulp_href",
            "name",
            "last_refreshed",
            "paths",
            "remote",
        )


class AlternateContentSourcePathSerializer(ModelSerializer):
    """
    Serializer for the AlternateContentSourcePath.
    """

    alternate_content_source = DetailRelatedField(
        view_name_pattern=r"acs(-.*/.*)-detail",
        queryset=models.AlternateContentSource.objects.all(),
        required=True,
    )
    path = serializers.CharField(help_text=_("Path for ACS."), allow_blank=True, required=False)
    repository = DetailRelatedField(
        view_name_pattern=r"repository(-.*/.*)-detail",
        queryset=models.Repository.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate_path(self, value):
        if value == "":
            return value
        if value.startswith("/"):
            raise serializers.ValidationError(_("Path cannot start with a slash."))
        if not value.endswith("/"):
            raise serializers.ValidationError(_("Path should end with a trailing slash."))
        return value

    class Meta:
        model = models.AlternateContentSourcePath
        fields = ModelSerializer.Meta.fields + ("alternate_content_source", "path", "repository")
