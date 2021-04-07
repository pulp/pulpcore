from gettext import gettext as _

from django.db.models import Q
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models
from pulpcore.app.loggers import deprecation_logger
from pulpcore.app.serializers import (
    BaseURLField,
    DetailIdentityField,
    DetailRelatedField,
    LabelsField,
    ModelSerializer,
    RepositoryVersionRelatedField,
    validate_unknown_fields,
)


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
        if hasattr(self, "initial_data"):
            validate_unknown_fields(self.initial_data, self.fields)

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

    name = serializers.CharField(help_text=_("The unique name."))
    description = serializers.CharField(
        help_text=_("An optional description."), allow_null=True, required=False
    )

    class Meta:
        model = models.ContentGuard
        fields = ModelSerializer.Meta.fields + ("name", "description")


class BasePathOverlapMixin:
    """An mixin that checks `BaseDistribution` and `Distribution` for overlapping base paths"""

    def _validate_path_overlap_per_model_cls(self, path, model_cls):
        # look for any base paths nested in path
        search = path.split("/")[0]
        q = Q(base_path=search)
        for subdir in path.split("/")[1:]:
            search = "/".join((search, subdir))
            q |= Q(base_path=search)

        # look for any base paths that nest path
        q |= Q(base_path__startswith="{}/".format(path))
        qs = model_cls.objects.filter(q)

        if self.instance is not None and isinstance(self.instance, model_cls):
            qs = qs.exclude(pk=self.instance.pk)

        match = qs.first()
        if match:
            raise serializers.ValidationError(
                detail=_("Overlaps with existing distribution '{}'").format(match.name)
            )

        return path

    def validate_base_path(self, path):
        self._validate_relative_path(path)
        self._validate_path_overlap_per_model_cls(path, models.BaseDistribution)
        return self._validate_path_overlap_per_model_cls(path, models.Distribution)


class BaseDistributionSerializer(ModelSerializer, BasePathOverlapMixin):
    """
    The Serializer for the BaseDistribution model.

    The serializer deliberately omits the "remote" field, which is used for
    pull-through caching only. Plugins implementing pull-through caching will
    have to add the field in their derived serializer class like this::

      remote = DetailRelatedField(
          required=False,
          help_text=_('Remote that can be used to fetch content when using pull-through caching.'),
          queryset=models.Remote.objects.all(),
          allow_null=True
      )

    """

    pulp_href = DetailIdentityField(view_name_pattern=r"distributions(-.*/.*)-detail")
    pulp_labels = LabelsField(required=False)
    base_path = serializers.CharField(
        help_text=_(
            'The base (relative) path component of the published url. Avoid paths that \
                    overlap with other distribution base paths (e.g. "foo" and "foo/bar")'
        ),
        validators=[UniqueValidator(queryset=models.BaseDistribution.objects.all())],
    )
    base_url = BaseURLField(
        source="base_path",
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
        validators=[
            UniqueValidator(queryset=models.BaseDistribution.objects.all()),
            UniqueValidator(queryset=models.Distribution.objects.all()),
        ],
    )

    def __init__(self, *args, **kwargs):
        """ Initialize a BaseDistributionSerializer and emit deprecation warnings"""
        deprecation_logger.warn(
            _(
                "BaseDistributionSerializer is deprecated and could be removed as early as "
                "pulpcore==3.13; use pulpcore.plugin.serializers.DistributionSerializer instead."
            )
        )
        return super().__init__(*args, **kwargs)

    class Meta:
        abstract = True
        model = models.BaseDistribution
        fields = ModelSerializer.Meta.fields + (
            "base_path",
            "base_url",
            "content_guard",
            "pulp_labels",
            "name",
        )


class DistributionSerializer(ModelSerializer, BasePathOverlapMixin):
    """
    The Serializer for the Distribution model.

    The serializer deliberately omits the the `publication` and `repository_version` field due to
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
    pulp_labels = LabelsField(required=False)

    base_path = serializers.CharField(
        help_text=_(
            'The base (relative) path component of the published url. Avoid paths that \
                    overlap with other distribution base paths (e.g. "foo" and "foo/bar")'
        ),
    )
    base_url = BaseURLField(
        source="base_path",
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
        validators=[
            UniqueValidator(queryset=models.BaseDistribution.objects.all()),
            UniqueValidator(queryset=models.Distribution.objects.all()),
        ],
    )
    repository = DetailRelatedField(
        required=False,
        help_text=_("The latest RepositoryVersion for this Repository will be served."),
        view_name_pattern=r"repositories(-.*/.*)?-detail",
        queryset=models.Repository.objects.all(),
        allow_null=True,
    )

    class Meta:
        abstract = True
        model = models.BaseDistribution
        fields = ModelSerializer.Meta.fields + (
            "base_path",
            "base_url",
            "content_guard",
            "pulp_labels",
            "name",
            "repository",
        )

    def validate(self, data):
        super().validate(data)

        publication_in_data = "publication" in data
        repository_version_in_data = "repository_version" in data
        publication_in_instance = self.instance.publication if self.instance else None
        repository_version_in_instance = self.instance.repository_version if self.instance else None

        if publication_in_data and repository_version_in_data:
            error = True
        elif publication_in_data and repository_version_in_instance:
            error = True
        elif publication_in_instance and repository_version_in_data:
            error = True
        else:
            error = False

        if error:
            msg = _(
                "Only one of the attributes 'publication' and 'repository_version' may be used "
                "simultaneously."
            )
            raise serializers.ValidationError(msg)

        return data


class PublicationDistributionSerializer(BaseDistributionSerializer):
    publication = DetailRelatedField(
        required=False,
        help_text=_("Publication to be served"),
        view_name_pattern=r"publications(-.*/.*)?-detail",
        queryset=models.Publication.objects.exclude(complete=False),
        allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        """ Initialize a PublicationDistributionSerializer and emit deprecation warnings"""
        deprecation_logger.warn(
            _(
                "PublicationDistributionSerializer is deprecated and could be removed as early as "
                "pulpcore==3.13; use pulpcore.plugin.serializers.DistributionSerializer instead. "
                "See its docstring for more details."
            )
        )
        return super().__init__(*args, **kwargs)

    class Meta:
        abstract = True
        fields = BaseDistributionSerializer.Meta.fields + ("publication",)


class RepositoryVersionDistributionSerializer(BaseDistributionSerializer):
    repository = DetailRelatedField(
        required=False,
        help_text=_("The latest RepositoryVersion for this Repository will be served."),
        view_name_pattern=r"repositories(-.*/.*)?-detail",
        queryset=models.Repository.objects.all(),
        allow_null=True,
    )
    repository_version = RepositoryVersionRelatedField(
        required=False, help_text=_("RepositoryVersion to be served"), allow_null=True
    )

    def __init__(self, *args, **kwargs):
        """ Initialize a RepositoryVersionDistributionSerializer and emit deprecation warnings"""
        deprecation_logger.warn(
            _(
                "PublicationDistributionSerializer is deprecated and could be removed as early as "
                "pulpcore==3.13; use pulpcore.plugin.serializers.DistributionSerializer instead. "
                "See its docstring for more details."
            )
        )
        return super().__init__(*args, **kwargs)

    class Meta:
        abstract = True
        fields = BaseDistributionSerializer.Meta.fields + ("repository", "repository_version")

    def validate(self, data):
        super().validate(data)

        repository_in_data = "repository" in data
        repository_version_in_data = "repository_version" in data
        repository_in_instance = self.instance.repository if self.instance else None
        repository_version_in_instance = self.instance.repository_version if self.instance else None

        if repository_in_data and repository_version_in_data:
            error = True
        elif repository_in_data and repository_version_in_instance:
            error = True
        elif repository_in_instance and repository_version_in_data:
            error = True
        else:
            error = False

        if error:
            msg = _(
                "Only one of the attributes 'publication' and 'repository_version' may be used "
                "simultaneously."
            )
            raise serializers.ValidationError(msg)

        return data
