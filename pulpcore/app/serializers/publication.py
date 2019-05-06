from gettext import gettext as _

from django.core import validators
from django.db.models import Q

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.app import models
from pulpcore.app.serializers import (
    BaseURLField,
    DetailIdentityField,
    DetailRelatedField,
    NestedRelatedField,
    RelatedField,
    MasterModelSerializer,
    ModelSerializer,
    validate_unknown_fields,
)


class PublicationSerializer(MasterModelSerializer):
    _href = DetailIdentityField()
    _distributions = DetailRelatedField(
       help_text=_('This publication is currently being served as'
                   'defined by these distributions.'),
       many=True,
       read_only=True,
    )
    repository_version = NestedRelatedField(
        view_name='versions-detail',
        lookup_field='number',
        parent_lookup_kwargs={'repository_pk': 'repository__pk'},
        queryset=models.RepositoryVersion.objects.all(),
        required=False,
    )
    repository = serializers.HyperlinkedRelatedField(
        help_text=_('A URI of the repository to be published.'),
        required=False,
        label=_('Repository'),
        queryset=models.Repository.objects.all(),
        view_name='repositories-detail',
    )

    def validate(self, data):
        if hasattr(self, 'initial_data'):
            validate_unknown_fields(self.initial_data, self.fields)

        repository = data.pop('repository', None)  # not an actual field on publication
        repository_version = data.get('repository_version')
        if not repository and not repository_version:
            raise serializers.ValidationError(
                _("Either the 'repository' or 'repository_version' need to be specified"))
        elif not repository and repository_version:
            return data
        elif repository and not repository_version:
            version = models.RepositoryVersion.latest(repository)
            if version:
                new_data = {'repository_version': version}
                new_data.update(data)
                return new_data
            else:
                raise serializers.ValidationError(
                    detail=_('Repository has no version available to create Publication from'))
        raise serializers.ValidationError(
            _("Either the 'repository' or 'repository_version' need to be specified "
              "but not both.")
        )

    class Meta:
        abstract = True
        model = models.Publication
        fields = MasterModelSerializer.Meta.fields + (
            'publisher',
            '_distributions',
            'repository_version',
            'repository'
        )


class ContentGuardSerializer(MasterModelSerializer):
    _href = DetailIdentityField()

    name = serializers.CharField(
        help_text=_('The unique name.')
    )
    description = serializers.CharField(
        help_text=_('An optional description.'),
        allow_blank=True,
        required=False
    )

    class Meta:
        model = models.ContentGuard
        fields = MasterModelSerializer.Meta.fields + (
            'name',
            'description'
        )


class BaseDistributionSerializer(MasterModelSerializer):
    _href = DetailIdentityField()
    content_guard = DetailRelatedField(
        required=False,
        help_text=_('An optional content-guard.'),
        queryset=models.ContentGuard.objects.all(),
        allow_null=True
    )
    name = serializers.CharField(
        help_text=_('A unique distribution name. Ex, `rawhide` and `stable`.'),
        validators=[validators.MaxLengthValidator(
            models.Distribution._meta.get_field('name').max_length,
            message=_('Distribution name length must be less than {} characters').format(
                models.Distribution._meta.get_field('name').max_length
            )),
            UniqueValidator(queryset=models.Distribution.objects.all())]
    )
    remote = DetailRelatedField(
        required=False,
        help_text=_('Remote that can be used to fetch content when using pull-through caching.'),
        queryset=models.Remote.objects.all(),
        allow_null=True
    )

    class Meta:
        fields = ModelSerializer.Meta.fields + (
            'content_guard',
            'name',
            'remote',
        )


class DistributionSerializer(BaseDistributionSerializer):
    base_path = serializers.CharField(
        help_text=_('The base (relative) path component of the published url. Avoid paths that \
                    overlap with other distribution base paths (e.g. "foo" and "foo/bar")'),
        validators=[validators.MaxLengthValidator(
            models.Distribution._meta.get_field('base_path').max_length,
            message=_('Distribution base_path length must be less than {} characters').format(
                models.Distribution._meta.get_field('base_path').max_length
            )),
            UniqueValidator(queryset=models.Distribution.objects.all()),
        ]
    )
    base_url = BaseURLField(
        source='base_path', read_only=True,
        help_text=_('The URL for accessing the publication as defined by this distribution.')
    )
    publication = DetailRelatedField(
        required=False,
        help_text=_('Publication to be served'),
        queryset=models.Publication.objects.exclude(complete=False),
        allow_null=True
    )
    repository = RelatedField(
        required=False,
        help_text=_('The latest RepositoryVersion for this Repository will be served.'),
        queryset=models.Repository.objects.all(),
        view_name='repositories-detail',
        allow_null=True
    )
    repository_version = NestedRelatedField(
        required=False,
        help_text=_('RepositoryVersion to be served'),
        queryset=models.RepositoryVersion.objects.exclude(complete=False),
        view_name='versions-detail',
        allow_null=True,
        lookup_field='number',
        parent_lookup_kwargs={'repository_pk': 'repository__pk'},
    )

    class Meta:
        model = models.Distribution
        fields = BaseDistributionSerializer.Meta.fields + (
            'base_path',
            'base_url',
            'publication',
            'repository',
            'repository_version',
        )

    def _validate_path_overlap(self, path):
        # look for any base paths nested in path
        search = path.split("/")[0]
        q = Q(base_path=search)
        for subdir in path.split("/")[1:]:
            search = "/".join((search, subdir))
            q |= Q(base_path=search)

        # look for any base paths that nest path
        q |= Q(base_path__startswith='{}/'.format(path))
        qs = models.Distribution.objects.filter(q)

        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        match = qs.first()
        if match:
            raise serializers.ValidationError(detail=_("Overlaps with existing distribution '"
                                                       "{}'").format(match.name))

        return path

    def validate_base_path(self, path):
        self._validate_relative_path(path)
        return self._validate_path_overlap(path)

    def validate(self, data):
        super().validate(data)

        mutex_keys = ['publication', 'repository', 'repository_version']
        in_use_keys = []
        for mkey in mutex_keys:
            if mkey in data:
                in_use_keys.append(mkey)

        if len(in_use_keys) > 1:
            msg = _("The attributes {keys} must be used exclusively.".format(keys=in_use_keys))
            raise serializers.ValidationError(msg)

        return data
