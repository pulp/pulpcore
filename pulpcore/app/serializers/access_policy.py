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
        ),
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

    class Meta:
        model = models.AccessPolicy
        fields = ModelSerializer.Meta.fields + (
            "permissions_assignment",
            "statements",
            "viewset_name",
            "customized",
        )

    def validate(self, data):
        """ "
        Validate the AccessPolicy.

        This ensures that the customized boolean will be set to True anytime the user modifies it.
        """
        data = super().validate(data)
        if data:
            data["customized"] = True
        return data
