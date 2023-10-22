from gettext import gettext as _

from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from pulpcore.app import models
from pulpcore.app.serializers import (
    BaseURLField,
    DetailIdentityField,
    DetailRelatedField,
    DomainUniqueValidator,
    GetOrCreateSerializerMixin,
    ModelSerializer,
    RepositoryVersionRelatedField,
    pulp_labels_validator,
)
from pulpcore.app.serializers.user import GroupUserSerializer, GroupSerializer
from pulpcore.app.role_util import get_users_with_perms, get_groups_with_perms
from pulpcore.app.util import get_domain


class PublicationSerializer(ModelSerializer):
    pulp_href = DetailIdentityField(view_name_pattern=r"publications(-.*/.*)-detail")
    repository_version = RepositoryVersionRelatedField(required=False)
    repository = DetailRelatedField(
        help_text=_("A URI of the repository to be published."),
        required=False,
        label=_("Repository"),
        view_name_pattern=r"repositories(-.*/.*)?-detail",
        queryset=models.Repository.objects.all(),
    )

    def validate(self, data):
        data = super().validate(data)

        repository = data.pop("repository", None)  # not an actual field on publication
        repository_version = data.get("repository_version")
        if not repository and not repository_version:
            raise serializers.ValidationError(
                _("Either the 'repository' or 'repository_version' need to be specified")
            )
        elif not repository and repository_version:
            return data
        elif repository and not repository_version:
            version = repository.latest_version()
            if version:
                new_data = {"repository_version": version}
                new_data.update(data)
                return new_data
            else:
                raise serializers.ValidationError(
                    detail=_("Repository has no version available to create Publication from")
                )
        raise serializers.ValidationError(
            _(
                "Either the 'repository' or 'repository_version' need to be specified "
                "but not both."
            )
        )

    class Meta:
        abstract = True
        model = models.Publication
        fields = ModelSerializer.Meta.fields + ("repository_version", "repository")


class ContentGuardSerializer(ModelSerializer):
    pulp_href = DetailIdentityField(view_name_pattern=r"contentguards(-.*/.*)-detail")

    name = serializers.CharField(
        help_text=_("The unique name."),
        validators=[DomainUniqueValidator(queryset=models.ContentGuard.objects.all())],
    )
    description = serializers.CharField(
        help_text=_("An optional description."), allow_null=True, required=False
    )

    class Meta:
        model = models.ContentGuard
        fields = ModelSerializer.Meta.fields + ("name", "description")


class RBACContentGuardSerializer(ContentGuardSerializer):
    users = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()

    @extend_schema_field(GroupUserSerializer(many=True))
    def get_users(self, obj):
        """Finds all the users with this object's download permission."""
        users = get_users_with_perms(
            obj, with_group_users=False, only_with_perms_in=["download_rbaccontentguard"]
        )
        return GroupUserSerializer(users, many=True, context=self.context).data

    @extend_schema_field(GroupSerializer(many=True))
    def get_groups(self, obj):
        """Finds all the groups with this object's download permission."""
        groups = get_groups_with_perms(obj, attach_perms=True)
        return GroupSerializer(
            (group for group, perms in groups.items() if "download_rbaccontentguard" in perms),
            many=True,
            context=self.context,
        ).data

    class Meta:
        model = models.RBACContentGuard
        fields = ContentGuardSerializer.Meta.fields + ("users", "groups")


class CompositeContentGuardSerializer(ContentGuardSerializer, GetOrCreateSerializerMixin):
    guards = DetailRelatedField(
        many=True,
        required=False,
        help_text=_("List of ContentGuards to ask for access-permission."),
        view_name_pattern=r"contentguards(-.*/.*)?-detail",
        queryset=models.ContentGuard.objects.all(),
        allow_null=True,
    )

    class Meta:
        model = models.CompositeContentGuard
        fields = ContentGuardSerializer.Meta.fields + ("guards",)


class RBACContentGuardPermissionSerializer(serializers.Serializer):
    usernames = serializers.ListField(default=[])
    groupnames = serializers.ListField(default=[])


class ContentRedirectContentGuardSerializer(ContentGuardSerializer, GetOrCreateSerializerMixin):
    """
    A serializer for ContentRedirectContentGuard.
    """

    class Meta(ContentGuardSerializer.Meta):
        model = models.ContentRedirectContentGuard


class HeaderContentGuardSerializer(ContentGuardSerializer, GetOrCreateSerializerMixin):
    """
    A serializer for HeaderContentGuard.
    """

    header_name = serializers.CharField(help_text=_("The header name the guard will check on."))
    header_value = serializers.CharField(help_text=_("The value that will authorize the request."))
    jq_filter = serializers.CharField(
        help_text=_(
            (
                "A JQ syntax compatible filter. If jq_filter is not set, then the value will"
                "only be Base64 decoded and checked as an explicit string match."
            )
        ),
        allow_null=True,
        required=False,
    )

    class Meta(ContentGuardSerializer.Meta):
        model = models.HeaderContentGuard
        fields = ContentGuardSerializer.Meta.fields + ("header_name", "header_value", "jq_filter")


class DistributionSerializer(ModelSerializer):
    """
    The Serializer for the Distribution model.

    The serializer deliberately omits the `publication` and `repository_version` field due to
    plugins typically requiring one or the other but not both.

    To include the ``publication`` field, it is recommended plugins define the field::

      publication = DetailRelatedField(
          required=False,
          help_text=_("Publication to be served"),
          view_name_pattern=r"publications(-.*/.*)?-detail",
          queryset=models.Publication.objects.exclude(complete=False),
          allow_null=True,
      )

    To include the ``repository_version`` field, it is recommended plugins define the field::

      repository_version = RepositoryVersionRelatedField(
          required=False, help_text=_("RepositoryVersion to be served"), allow_null=True
      )

    Additionally, the serializer omits the ``remote`` field, which is used for pull-through caching
    feature and only by plugins which use publications. Plugins implementing a pull-through caching
    should define the field in their derived serializer class like this::

      remote = DetailRelatedField(
          required=False,
          help_text=_('Remote that can be used to fetch content when using pull-through caching.'),
          queryset=models.Remote.objects.all(),
          allow_null=True
      )

    """

    pulp_href = DetailIdentityField(view_name_pattern=r"distributions(-.*/.*)-detail")
    pulp_labels = serializers.HStoreField(required=False, validators=[pulp_labels_validator])

    base_path = serializers.CharField(
        help_text=_(
            'The base (relative) path component of the published url. Avoid paths that \
                    overlap with other distribution base paths (e.g. "foo" and "foo/bar")'
        ),
        validators=[DomainUniqueValidator(queryset=models.Distribution.objects.all())],
    )
    base_url = BaseURLField(
        source="*",
        read_only=True,
        help_text=_("The URL for accessing the publication as defined by this distribution."),
    )
    content_guard = DetailRelatedField(
        required=False,
        help_text=_("An optional content-guard."),
        view_name_pattern=r"contentguards(-.*/.*)?-detail",
        queryset=models.ContentGuard.objects.all(),
        allow_null=True,
    )
    name = serializers.CharField(
        help_text=_("A unique name. Ex, `rawhide` and `stable`."),
        validators=[DomainUniqueValidator(queryset=models.Distribution.objects.all())],
    )
    repository = DetailRelatedField(
        required=False,
        help_text=_("The latest RepositoryVersion for this Repository will be served."),
        view_name_pattern=r"repositories(-.*/.*)?-detail",
        queryset=models.Repository.objects.all(),
        allow_null=True,
    )
    hidden = serializers.BooleanField(
        default=False, help_text=_("Whether this distribution should be shown in the content app.")
    )

    class Meta:
        model = models.Distribution
        fields = ModelSerializer.Meta.fields + (
            "base_path",
            "base_url",
            "content_guard",
            "hidden",
            "pulp_labels",
            "name",
            "repository",
        )

    def _validate_path_overlap(self, path):
        # look for any base paths nested in path
        search = path.split("/")[0]
        q = Q(base_path=search)
        for subdir in path.split("/")[1:]:
            search = "/".join((search, subdir))
            q |= Q(base_path=search)

        # look for any base paths that nest path
        q |= Q(base_path__startswith="{}/".format(path))
        qs = models.Distribution.objects.filter(q & Q(pulp_domain=get_domain()))

        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        match = qs.first()
        if match:
            raise serializers.ValidationError(
                detail={
                    "base_path": _("Overlaps with existing distribution '{}'").format(match.name)
                },
            )

        return path

    def validate_base_path(self, path):
        self._validate_relative_path(path)
        return self._validate_path_overlap(path)

    def validate(self, data):
        super().validate(data)

        repository_provided = data.get(
            "repository", (self.partial and self.instance.repository) or None
        )
        repository_version_provided = data.get(
            "repository_version", (self.partial and self.instance.repository_version) or None
        )
        publication_provided = data.get(
            "publication", (self.partial and self.instance.publication) or None
        )

        if publication_provided and repository_version_provided:
            raise serializers.ValidationError(
                _(
                    "Only one of the attributes 'publication' and 'repository_version' "
                    "may be used simultaneously."
                )
            )
        elif repository_provided and repository_version_provided:
            raise serializers.ValidationError(
                _(
                    "Only one of the attributes 'repository' and 'repository_version' "
                    "may be used simultaneously."
                )
            )

        elif repository_provided and publication_provided:
            raise serializers.ValidationError(
                _(
                    "Only one of the attributes 'repository' and 'publication' "
                    "may be used simultaneously."
                )
            )

        return data


class ArtifactDistributionSerializer(DistributionSerializer):
    """
    A serializer for ArtifactDistribution.
    """

    class Meta:
        model = models.ArtifactDistribution
        fields = tuple(
            set(DistributionSerializer.Meta.fields)
            - {
                "repository",
            }
        )
