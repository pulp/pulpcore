from gettext import gettext as _

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models
from pulpcore.app.serializers import IdentityField, ModelSerializer


class AccessPolicySerializer(ModelSerializer):
    """Serializer for AccessPolicy."""

    pulp_href = IdentityField(view_name="access_policies-detail")

    permissions_assignment = serializers.ListField(
        child=serializers.DictField(),
        help_text=_(
            "List of callables that define the new permissions to be created for new objects."
            "This is deprecated. Use `creation_hooks` instead."
        ),
        source="creation_hooks",
        required=False,
    )

    creation_hooks = serializers.ListField(
        child=serializers.DictField(),
        help_text=_("List of callables that may associate user roles for new objects."),
        required=False,
    )

    statements = serializers.ListField(
        child=serializers.DictField(),
        help_text=_("List of policy statements defining the policy."),
    )

    viewset_name = serializers.CharField(
        help_text=_("The name of ViewSet this AccessPolicy authorizes."),
        validators=[UniqueValidator(queryset=models.AccessPolicy.objects.all())],
        read_only=True,
    )

    customized = serializers.BooleanField(
        help_text=_("True if the AccessPolicy has been user-modified. False otherwise."),
        read_only=True,
    )

    queryset_scoping = serializers.DictField(
        help_text=_(
            "A callable for performing queryset scoping. See plugin documentation for valid"
            " callables. Set to blank to turn off queryset scoping."
        ),
        required=False,
    )

    class Meta:
        model = models.AccessPolicy
        fields = ModelSerializer.Meta.fields + (
            "permissions_assignment",
            "creation_hooks",
            "statements",
            "viewset_name",
            "customized",
            "queryset_scoping",
        )

    def validate(self, data):
        """
        Validate the AccessPolicy.

        This ensures that the customized boolean will be set to True anytime the user modifies it.
        """
        data = super().validate(data)
        if "permissions_assignment" in data:
            if "creation_hooks" in data:
                if data["creation_hooks"] != data["permissions_assignment"]:
                    raise serializers.ValidationError(
                        detail=_(
                            "Cannot specify both 'permissions_assignment' and 'creation_hooks'."
                        )
                    )
            data["creation_hooks"] = data.pop("permissions_assignment")

        if data:
            data["customized"] = True
        return data
