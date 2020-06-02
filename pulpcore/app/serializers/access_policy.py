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
    )

    class Meta:
        model = models.AccessPolicy
        fields = ModelSerializer.Meta.fields + (
            "permissions_assignment",
            "statements",
            "viewset_name",
        )
