from gettext import gettext as _

from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import (
    DetailRelatedField,
    DomainUniqueValidator,
    IdentityField,
    ModelSerializer,
    RepositoryVersionRelatedField,
    pulp_labels_validator,
)
from pulpcore.app.util_content_view import resolve_content_view_distributions


class ContentViewDistributionStatusSerializer(serializers.Serializer):
    """Per-distribution resolution status, shown on the ContentView detail/list endpoints."""

    distribution = DetailRelatedField(
        read_only=True,
        view_name_pattern=r"distributions(-.*/.*)?-detail",
        help_text=_("The distribution this status entry describes."),
    )
    domain = serializers.CharField(
        source="domain.name", help_text=_("The name of the domain the distribution belongs to.")
    )
    status = serializers.ChoiceField(
        choices=["ok", "no_domain_access", "no_version"],
        help_text=_(
            "'ok' if the distribution currently resolves to a repository version the caller can "
            "search; 'no_domain_access' if the caller does not (or no longer) have read access "
            "to the distribution's domain; 'no_version' if the distribution or the repository "
            "version/publication it pointed to has been deleted."
        ),
    )
    repository_version = RepositoryVersionRelatedField(
        read_only=True,
        allow_null=True,
        queryset=None,
        help_text=_("The repository version currently resolved for this distribution, if any."),
    )


class ContentViewSerializer(ModelSerializer):
    """
    Serializer for a ContentView -- a named, persistable scope composed of Distributions that
    may span multiple domains, used to search across their content without exposing raw
    repository version hrefs on every request.
    """

    # Distributions referenced by a ContentView may legitimately live in a domain other than
    # the ContentView's own -- that's the entire point of this resource -- so the default
    # same-domain cross-field validation (ValidateFieldsMixin.check_cross_domains) must not
    # apply here.
    CHECK_SAME_DOMAIN = False

    pulp_href = IdentityField(view_name="content-views-detail")

    name = serializers.CharField(
        help_text=_("A unique name for this content view."),
        validators=[DomainUniqueValidator(queryset=models.ContentView.objects.all())],
    )
    description = serializers.CharField(
        help_text=_("An optional description of this content view."),
        required=False,
        allow_null=True,
    )
    pulp_labels = serializers.HStoreField(required=False, validators=[pulp_labels_validator])
    distributions = DetailRelatedField(
        many=True,
        required=False,
        queryset=models.Distribution.objects.all(),
        view_name_pattern=r"distributions(-.*/.*)?-detail",
        help_text=_(
            "Distributions this content view searches across. May reference distributions "
            "belonging to any domain the user has read access to, not just this content view's "
            "own domain."
        ),
    )
    distributions_status = serializers.SerializerMethodField(
        help_text=_(
            "Per-distribution resolution status: whether each linked distribution's domain is "
            "currently accessible and whether it resolves to a repository version."
        )
    )

    def get_distributions_status(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user is None:
            return []
        resolutions = resolve_content_view_distributions(obj, user)
        return ContentViewDistributionStatusSerializer(
            resolutions, many=True, context=self.context
        ).data

    class Meta:
        model = models.ContentView
        fields = ModelSerializer.Meta.fields + (
            "name",
            "description",
            "pulp_labels",
            "distributions",
            "distributions_status",
        )
