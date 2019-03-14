from gettext import gettext as _

from rest_framework import serializers, fields
from rest_framework.validators import UniqueValidator
from rest_framework_nested.serializers import NestedHyperlinkedModelSerializer

from pulpcore.app import models
from pulpcore.app.serializers import (
    DetailIdentityField,
    IdentityField,
    NestedIdentityField,
    NestedRelatedField,
    LatestVersionField,
    MasterModelSerializer,
    ModelSerializer,
)
from pulpcore.app.serializers import validate_unknown_fields


class RepositorySerializer(ModelSerializer):
    _href = IdentityField(
        view_name='repositories-detail'
    )
    _versions_href = IdentityField(
        view_name='versions-list',
        lookup_url_kwarg='repository_pk',
    )
    _latest_version_href = LatestVersionField()
    name = serializers.CharField(
        help_text=_('A unique name for this repository.'),
        validators=[UniqueValidator(queryset=models.Repository.objects.all())]
    )
    description = serializers.CharField(
        help_text=_('An optional description.'),
        required=False,
        allow_blank=True
    )

    class Meta:
        model = models.Repository
        fields = ModelSerializer.Meta.fields + ('_versions_href', '_latest_version_href', 'name',
                                                'description')


class RemoteSerializer(MasterModelSerializer):
    """
    Every remote defined by a plugin should have a Remote serializer that inherits from this
    class. Please import from `pulpcore.plugin.serializers` rather than from this module directly.
    """
    _href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_('A unique name for this remote.'),
        validators=[UniqueValidator(queryset=models.Remote.objects.all())],
    )
    url = serializers.CharField(
        help_text='The URL of an external content source.',
    )
    validate = serializers.BooleanField(
        help_text='If True, the plugin will validate imported artifacts.',
        required=False,
    )
    ssl_ca_certificate = serializers.FileField(
        help_text='A PEM encoded CA certificate used to validate the server '
                  'certificate presented by the remote server.',
        write_only=True,
        required=False,
    )
    ssl_client_certificate = serializers.FileField(
        help_text='A PEM encoded client certificate used for authentication.',
        write_only=True,
        required=False,
    )
    ssl_client_key = serializers.FileField(
        help_text='A PEM encoded private key used for authentication.',
        write_only=True,
        required=False,
    )
    ssl_validation = serializers.BooleanField(
        help_text='If True, SSL peer validation must be performed.',
        required=False,
    )
    proxy_url = serializers.CharField(
        help_text='The proxy URL. Format: scheme://user:password@host:port',
        required=False,
        allow_blank=True,
    )
    username = serializers.CharField(
        help_text='The username to be used for authentication when syncing.',
        write_only=True,
        required=False,
        allow_blank=True,
    )
    password = serializers.CharField(
        help_text='The password to be used for authentication when syncing.',
        write_only=True,
        required=False,
        allow_blank=True,
    )
    _last_updated = serializers.DateTimeField(
        help_text='Timestamp of the most recent update of the remote.',
        read_only=True
    )
    download_concurrency = serializers.IntegerField(
        help_text='Total number of simultaneous connections.',
        required=False,
        min_value=1
    )
    policy = serializers.ChoiceField(
        help_text="The policy to use when downloading content. The possible values include: "
                  "'immediate', 'on_demand', and 'cache_only'. 'immediate' is the default.",
        choices=models.Remote.POLICY_CHOICES,
        default=models.Remote.IMMEDIATE
    )

    class Meta:
        abstract = True
        model = models.Remote
        fields = MasterModelSerializer.Meta.fields + (
            'name', 'url', 'validate', 'ssl_ca_certificate', 'ssl_client_certificate',
            'ssl_client_key', 'ssl_validation', 'proxy_url', 'username', 'password',
            '_last_updated', 'download_concurrency', 'policy')


class RepositorySyncURLSerializer(serializers.Serializer):
    repository = serializers.HyperlinkedRelatedField(
        required=True,
        help_text=_('A URI of the repository to be synchronized.'),
        queryset=models.Repository.objects.all(),
        view_name='repositories-detail',
        label=_('Repository'),
        error_messages={
            'required': _('The repository URI must be specified.')
        }
    )

    mirror = fields.BooleanField(
        required=False,
        default=False,
        help_text=_('The synchronization mode, True for "mirror" and False for "additive" mode.')
    )


class PublisherSerializer(MasterModelSerializer):
    """
    Every publisher defined by a plugin should have an Publisher serializer that inherits from this
    class. Please import from `pulpcore.plugin.serializers` rather than from this module directly.
    """
    _href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_('A unique name for this publisher.'),
        validators=[UniqueValidator(queryset=models.Publisher.objects.all())]
    )
    _last_updated = serializers.DateTimeField(
        help_text=_('Timestamp of the most recent update of the publisher configuration.'),
        read_only=True
    )
    _distributions = serializers.HyperlinkedRelatedField(
        many=True,
        read_only=True,
        view_name='distributions-detail',
    )

    class Meta:
        abstract = True
        model = models.Publisher
        fields = MasterModelSerializer.Meta.fields + (
            'name', '_last_updated', '_distributions',
        )


class RepositoryPublishURLSerializer(serializers.Serializer):

    repository = serializers.HyperlinkedRelatedField(
        help_text=_('A URI of the repository to be synchronized.'),
        required=False,
        label=_('Repository'),
        queryset=models.Repository.objects.all(),
        view_name='repositories-detail',
    )

    repository_version = NestedRelatedField(
        help_text=_('A URI of the repository version to be published.'),
        required=False,
        label=_('Repository Version'),
        queryset=models.RepositoryVersion.objects.all(),
        view_name='versions-detail',
        lookup_field='number',
        parent_lookup_kwargs={'repository_pk': 'repository__pk'},
    )

    def validate(self, data):
        if hasattr(self, 'initial_data'):
            validate_unknown_fields(self.initial_data, self.fields)

        repository = data.pop('repository', None)
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
                    detail=_('Repository has no version available to publish'))
        raise serializers.ValidationError(
            _("Either the 'repository' or 'repository_version' need to be specified "
              "but not both.")
        )


class ExporterSerializer(MasterModelSerializer):
    _href = DetailIdentityField()
    name = serializers.CharField(
        help_text=_('The exporter unique name.'),
        validators=[UniqueValidator(queryset=models.Exporter.objects.all())]
    )
    _last_updated = serializers.DateTimeField(
        help_text=_('Timestamp of the last update.'),
        read_only=True
    )
    last_export = serializers.DateTimeField(
        help_text=_('Timestamp of the last export.'),
        read_only=True
    )

    class Meta:
        abstract = True
        model = models.Exporter
        fields = MasterModelSerializer.Meta.fields + (
            'name',
            '_last_updated',
            'last_export',
        )


class RepositoryVersionSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    _href = NestedIdentityField(
        view_name='versions-detail',
        lookup_field='number', parent_lookup_kwargs={'repository_pk': 'repository__pk'},
    )
    number = serializers.IntegerField(
        read_only=True
    )
    base_version = NestedRelatedField(
        required=False,
        help_text=_('A repository version whose content was used as the initial set of content '
                    'for this repository version'),
        queryset=models.RepositoryVersion.objects.all(),
        view_name='versions-detail',
        lookup_field='number',
        parent_lookup_kwargs={'repository_pk': 'repository__pk'},
    )
    content_summary = serializers.SerializerMethodField(
        help_text=_('Various count summaries of the content in the version and the HREF to view '
                    'them.'),
        read_only=True,
    )

    def get_content_summary(self, obj):
        """
        The summary of contained content.

        Returns:
            dict:    {'added': {<_type>: {'count': <count>, 'href': <href>},
                      'removed': {<_type>: {'count': <count>, 'href': <href>},
                      'present': {<_type>: {'count': <count>, 'href': <href>},
                     }
        """
        to_return = {'added': {}, 'removed': {}, 'present': {}}
        for count_detail in obj.counts.all():
            count_type = count_detail.get_count_type_display()
            item_dict = {'count': count_detail.count, 'href': count_detail.content_href}
            to_return[count_type][count_detail.content_type] = item_dict
        return to_return

    class Meta:
        model = models.RepositoryVersion
        fields = ModelSerializer.Meta.fields + (
            '_href', 'number', 'base_version', 'content_summary',
        )


class RepositoryVersionCreateSerializer(ModelSerializer, NestedHyperlinkedModelSerializer):
    add_content_units = serializers.ListField(
        help_text=_('A list of content units to add to a new repository version'),
        write_only=True
    )
    remove_content_units = serializers.ListField(
        help_text=_('A list of content units to remove from the latest repository version'),
        write_only=True
    )
    base_version = NestedRelatedField(
        required=False,
        help_text=_('A repository version whose content will be used as the initial set of content '
                    'for the new repository version'),
        queryset=models.RepositoryVersion.objects.all(),
        view_name='versions-detail',
        lookup_field='number',
        parent_lookup_kwargs={'repository_pk': 'repository__pk'},
    )

    class Meta:
        model = models.RepositoryVersion
        fields = ['add_content_units', 'remove_content_units', 'base_version']
