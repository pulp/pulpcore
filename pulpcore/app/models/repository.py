"""
Repository related Django models.
"""
import django

from contextlib import suppress
from django.db import models
from django.db import transaction
from django.urls import reverse

from .base import Model, MasterModel
from .content import Content
from .task import CreatedResource

from pulpcore.app.models.storage import get_tls_path
from pulpcore.app.util import get_view_name_for_model
from pulpcore.exceptions import ResourceImmutableError


class Repository(Model):
    """
    Collection of content.

    Fields:

        name (models.CharField): The repository name.
        description (models.TextField): An optional description.
        last_version (models.PositiveIntegerField): A record of the last created version number.
            Used when a repository version is deleted so as not to create a new vesrion with the
            same version number.

    Relations:

        content (models.ManyToManyField): Associated content.
    """
    name = models.CharField(db_index=True, unique=True, max_length=255)
    description = models.TextField()
    last_version = models.PositiveIntegerField(default=0)
    content = models.ManyToManyField('Content', through='RepositoryContent',
                                     related_name='repositories')

    class Meta:
        verbose_name_plural = 'repositories'

    def natural_key(self):
        """
        Get the model's natural key.

        :return: The model's natural key.
        :rtype: tuple
        """
        return (self.name,)


class Remote(MasterModel):
    """
    A remote source for content.

    Fields:

        name (models.CharField): The remote name.
        url (models.TextField): The URL of an external content source.
        validate (models.BooleanField): If True, the plugin will validate imported files.
        ssl_ca_certificate (models.FileField): A PEM encoded CA certificate used to validate the
            server certificate presented by the external source.
        ssl_client_certificate (models.FileField): A PEM encoded client certificate used
            for authentication.
        ssl_client_key (models.FileField): A PEM encoded private key used for authentication.
        ssl_validation (models.BooleanField): If True, SSL peer validation must be performed.
        proxy_url (models.TextField): The optional proxy URL.
            Format: scheme://user:password@host:port
        username (models.TextField): The username to be used for authentication when syncing.
        password (models.TextField): The password to be used for authentication when syncing.
        download_concurrency (models.PositiveIntegerField): Total number of
            simultaneous connections.
        policy (models.TextField): The policy to use when downloading content.

    Relations:

        repository (models.ForeignKey): The repository that owns this Remote
    """
    TYPE = 'remote'

    # Constants for the ChoiceField 'policy'
    IMMEDIATE = 'immediate'
    ON_DEMAND = 'on_demand'
    STREAMED = 'streamed'

    POLICY_CHOICES = (
        (IMMEDIATE, 'When syncing, download all metadata and content now.'),
        (ON_DEMAND, 'When syncing, download metadata, but do not download content now. Instead, '
                    'download content as clients request it, and save it in Pulp to be served for '
                    'future client requests.'),
        (STREAMED, 'When syncing, download metadata, but do not download content now. Instead,'
                   'download content as clients request it, but never save it in Pulp. This causes '
                   'future requests for that same content to have to be downloaded again.')
    )

    def tls_storage_path(self, name):
        """
        Returns storage path for TLS file

        Args:
            name (str): Original name of the uploaded file.
        """
        return get_tls_path(self, name)

    name = models.CharField(db_index=True, unique=True, max_length=255)

    url = models.TextField()
    validate = models.BooleanField(default=True)

    ssl_ca_certificate = models.FileField(upload_to=tls_storage_path, max_length=255)
    ssl_client_certificate = models.FileField(upload_to=tls_storage_path,
                                              max_length=255)
    ssl_client_key = models.FileField(upload_to=tls_storage_path, max_length=255)
    ssl_validation = models.BooleanField(default=True)

    proxy_url = models.TextField()
    username = models.TextField()
    password = models.TextField()
    download_concurrency = models.PositiveIntegerField(default=20)
    policy = models.TextField(choices=POLICY_CHOICES, default=IMMEDIATE)

    class Meta:
        default_related_name = 'remotes'


class Publisher(MasterModel):
    """
    A content publisher.

    Fields:

        name (models.CharField): The publisher unique name.

    Relations:

    """
    TYPE = 'publisher'

    name = models.CharField(db_index=True, unique=True, max_length=255)

    class Meta:
        default_related_name = 'publishers'


class Exporter(MasterModel):
    """
    A publication exporter.

    Fields:

        name (models.CharField): The exporter unique name.
        last_export (models.DatetimeField): When the last successful export occurred.

    Relations:

    """
    TYPE = 'exporter'

    name = models.CharField(db_index=True, unique=True, max_length=255)
    last_export = models.DateTimeField(null=True)

    class Meta:
        default_related_name = 'exporters'


class RepositoryContent(Model):
    """
    Association between a repository and its contained content.

    Fields:

        created (models.DatetimeField): When the association was created.

    Relations:

        content (models.ForeignKey): The associated content.
        repository (models.ForeignKey): The associated repository.
        version_added (models.ForeignKey): The RepositoryVersion which added the referenced
            Content.
        version_removed (models.ForeignKey): The RepositoryVersion which removed the referenced
            Content.
    """
    content = models.ForeignKey('Content', on_delete=models.CASCADE,
                                related_name='version_memberships')
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    version_added = models.ForeignKey('RepositoryVersion', related_name='added_memberships',
                                      on_delete=models.CASCADE)
    version_removed = models.ForeignKey('RepositoryVersion', null=True,
                                        related_name='removed_memberships',
                                        on_delete=models.CASCADE)

    class Meta:
        unique_together = (('repository', 'content', 'version_added'),
                           ('repository', 'content', 'version_removed'))


class RepositoryVersion(Model):
    """
    A version of a repository's content set.

    Plugin Writers are strongly encouraged to use RepositoryVersion as a context manager to provide
    transactional safety, working directory set up, and cleaning up the database on failures.

    Examples:
        >>>
        >>> with RepositoryVersion.create(repository) as new_version:
        >>>     new_version.add_content(content_q)
        >>>     new_version.remove_content(content_q)
        >>>

    Fields:

        number (models.PositiveIntegerField): A positive integer that uniquely identifies a version
            of a specific repository. Each new version for a repo should have this field set to
            1 + the most recent version.
        action  (models.TextField): The action that produced the version.
        complete (models.BooleanField): If true, the RepositoryVersion is visible. This field is set
            to true when the task that creates the RepositoryVersion is complete.

    Relations:

        repository (models.ForeignKey): The associated repository.
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(db_index=True)
    complete = models.BooleanField(db_index=True, default=False)
    base_version = models.ForeignKey('RepositoryVersion', null=True,
                                     on_delete=models.SET_NULL)

    class Meta:
        default_related_name = 'versions'
        unique_together = ('repository', 'number')
        get_latest_by = 'number'
        ordering = ('number',)

    @property
    def content(self):
        """
        Returns a set of content for a repository version

        Returns:
            django.db.models.QuerySet: The content that is contained within this version.

        Examples:
            >>> repository_version = ...
            >>>
            >>> for content in repository_version.content:
            >>>     content = content.cast()  # optional downcast.
            >>>     ...
            >>>
            >>> for content in FileContent.objects.filter(pk__in=repository_version.content):
            >>>     ...
            >>>
        """
        relationships = RepositoryContent.objects.filter(
            repository=self.repository, version_added__number__lte=self.number
        ).exclude(
            version_removed__number__lte=self.number
        )
        return Content.objects.filter(version_memberships__in=relationships)

    def added(self):
        """
        Returns:
            QuerySet: The Content objects that were added by this version.
        """
        return Content.objects.filter(version_memberships__version_added=self)

    def removed(self):
        """
        Returns:
            QuerySet: The Content objects that were removed by this version.
        """
        return Content.objects.filter(version_memberships__version_removed=self)

    def contains(self, content):
        """
        Check whether a content exists in this repository version's set of content

        Returns:
            bool: True if the repository version contains the content, False otherwise
        """
        return self.content.filter(pk=content.pk).exists()

    @classmethod
    def create(cls, repository, base_version=None):
        """
        Create a new RepositoryVersion

        Creation of a RepositoryVersion should be done in a RQ Job.

        Args:
            repository (pulpcore.app.models.Repository): to create a new version of
            base_version (pulpcore.app.models.RepositoryVersion): an optional repository version
                whose content will be used as the set of content for the new version

        Returns:
            pulpcore.app.models.RepositoryVersion: The Created RepositoryVersion
        """
        with transaction.atomic():
            version = cls(
                repository=repository,
                number=int(repository.last_version) + 1,
                base_version=base_version)
            repository.last_version = version.number
            repository.save()
            version.save()

            if base_version:
                # first remove the content that isn't in the base version
                version.remove_content(version.content.exclude(pk__in=base_version.content))
                # now add any content that's in the base_version but not in version
                version.add_content(base_version.content.exclude(pk__in=version.content))

            resource = CreatedResource(content_object=version)
            resource.save()
            return version

    @staticmethod
    def latest(repository):
        """
        Get the latest RepositoryVersion on a repository

        Args:
            repository (pulpcore.app.models.Repository): to get the latest version of

        Returns:
            pulpcore.app.models.RepositoryVersion: The latest RepositoryVersion

        """
        with suppress(RepositoryVersion.DoesNotExist):
            model = repository.versions.exclude(complete=False).latest()
            return model

    def next(self):
        """
        Returns:
            pulpcore.app.models.RepositoryVersion: The next RepositoryVersion with the same
                repository.

        Raises:
            RepositoryVersion.DoesNotExist: if there is not a RepositoryVersion for the same
                repository and with a higher "number".
        """
        try:
            return self.repository.versions.exclude(complete=False).filter(
                number__gt=self.number).order_by('number')[0]
        except IndexError:
            raise self.DoesNotExist

    def add_content(self, content):
        """
        Add a content unit to this version.

        Args:
           content (django.db.models.QuerySet): Set of Content to add

        Raise:
            pulpcore.exception.ResourceImmutableError: if add_content is called on a
                complete RepositoryVersion
        """
        if self.complete:
            raise ResourceImmutableError(self)

        repo_content = []
        for content_pk in content.exclude(pk__in=self.content).values_list('pk', flat=True):
            repo_content.append(
                RepositoryContent(
                    repository=self.repository,
                    content_id=content_pk,
                    version_added=self
                )
            )

        RepositoryContent.objects.bulk_create(repo_content)

    def remove_content(self, content):
        """
        Remove content from the repository.

        Args:
            content (django.db.models.QuerySet): Set of Content to remove

        Raise:
            pulpcore.exception.ResourceImmutableError: if remove_content is called on a
                complete RepositoryVersion
        """

        if self.complete:
            raise ResourceImmutableError(self)

        q_set = RepositoryContent.objects.filter(
            repository=self.repository,
            content_id__in=content,
            version_removed=None)
        q_set.update(version_removed=self)

    def _squash(self, repo_relations, next_version):
        """
        Squash a complete repo version into the next version
        """
        # delete any relationships added in the version being deleted and removed in the next one.
        repo_relations.filter(version_added=self, version_removed=next_version).delete()

        # If the same content is deleted in version, but added back in next_version
        # set version_removed field in relation to None, and remove relation adding the content
        # in next_version
        content_added = repo_relations.filter(version_added=next_version).values_list('content_id')

        # use list() to force the evaluation of the queryset, otherwise queryset is affected
        # by the update() operation before delete() is ran
        content_removed_and_readded = list(repo_relations.filter(version_removed=self,
                                                                 content_id__in=content_added)
                                           .values_list('content_id'))

        repo_relations.filter(version_removed=self,
                              content_id__in=content_removed_and_readded)\
            .update(version_removed=None)

        repo_relations.filter(version_added=next_version,
                              content_id__in=content_removed_and_readded).delete()

        # "squash" by moving other additions and removals forward to the next version
        repo_relations.filter(version_added=self).update(version_added=next_version)
        repo_relations.filter(version_removed=self).update(version_removed=next_version)

    def delete(self, **kwargs):
        """
        Deletes a RepositoryVersion

        If RepositoryVersion is complete and has a successor, squash RepositoryContent changes into
        the successor. If version is incomplete, delete and and clean up RepositoryContent,
        CreatedResource, and Repository objects.

        Deletion of a complete RepositoryVersion should be done in a RQ Job.
        """
        if self.complete:
            repo_relations = RepositoryContent.objects.filter(repository=self.repository)
            try:
                next_version = self.next()
                self._squash(repo_relations, next_version)

            except RepositoryVersion.DoesNotExist:
                # version is the latest version so simply update repo contents
                # and delete the version
                repo_relations.filter(version_added=self).delete()
                repo_relations.filter(version_removed=self).update(version_removed=None)
            super().delete(**kwargs)

        else:
            with transaction.atomic():
                RepositoryContent.objects.filter(version_added=self).delete()
                RepositoryContent.objects.filter(version_removed=self) \
                    .update(version_removed=None)
                CreatedResource.objects.filter(object_id=self.pk).delete()
                self.repository.last_version = self.number - 1
                self.repository.save()
                super().delete(**kwargs)

    def compute_counts(self):
        """
        Compute and save content unit counts by type.

        Count records are stored as :class:`~pulpcore.app.models.RepositoryVersionContentDetails`.
        This method deletes existing :class:`~pulpcore.app.models.RepositoryVersionContentDetails`
        objects and makes new ones with each call.
        """
        with transaction.atomic():
            counts_list = []
            for value, name in RepositoryVersionContentDetails.COUNT_TYPE_CHOICES:
                RepositoryVersionContentDetails.objects.filter(repository_version=self).delete()
                if value == RepositoryVersionContentDetails.ADDED:
                    qs = self.added()
                elif value == RepositoryVersionContentDetails.PRESENT:
                    qs = self.content
                elif value == RepositoryVersionContentDetails.REMOVED:
                    qs = self.removed()
                annotated = qs.values('_type').annotate(count=models.Count('_type'))
                for item in annotated:
                    count_obj = RepositoryVersionContentDetails(
                        content_type=item['_type'],
                        repository_version=self,
                        count=item['count'],
                        count_type=value,
                    )
                    counts_list.append(count_obj)
            RepositoryVersionContentDetails.objects.bulk_create(counts_list)

    def __enter__(self):
        """
        Create the repository version

        Returns:
            RepositoryVersion: self
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Save the RepositoryVersion if no errors are raised, delete it if not
        """
        if exc_value:
            self.delete()
        else:
            self.complete = True
            self.save()
            self.compute_counts()

    def __str__(self):
        return "<Repository: {}; Version: {}>".format(self.repository.name, self.number)


class RepositoryVersionContentDetails(models.Model):
    ADDED = 'A'
    PRESENT = 'P'
    REMOVED = 'R'
    COUNT_TYPE_CHOICES = (
        (ADDED, 'added'),
        (PRESENT, 'present'),
        (REMOVED, 'removed'),
    )

    count_type = models.CharField(
        max_length=1,
        choices=COUNT_TYPE_CHOICES,
    )
    content_type = models.TextField()
    repository_version = models.ForeignKey('RepositoryVersion', related_name='counts',
                                           on_delete=models.CASCADE)
    count = models.IntegerField()

    @property
    def content_href(self):
        """
        Generate URLs for the content types present in the RepositoryVersion.

        For each content type present in the RepositoryVersion, create the URL of the viewset of
        that variety of content along with a query parameter which filters it by presence in this
        RepositoryVersion.

        Args:
            obj (pulpcore.app.models.RepositoryVersion): The RepositoryVersion being serialized.
        Returns:
            dict: {<_type>: <url>}
        """
        ctype_model = Content.objects.filter(_type=self.content_type).first().cast().__class__
        ctype_view = get_view_name_for_model(ctype_model, 'list')
        try:
            ctype_url = reverse(ctype_view)
        except django.urls.exceptions.NoReverseMatch:
            # We've hit a content type for which there is no viewset.
            # There's nothing we can do here, except to skip it.
            return
        rv_href = "/pulp/api/v3/repositories/{repo}/versions/{version}/".format(
            repo=self.repository_version.repository.pk, version=self.repository_version.number)
        if self.count_type == self.ADDED:
            partial_url_str = "{base}?repository_version_added={rv_href}"
        elif self.count_type == self.PRESENT:
            partial_url_str = "{base}?repository_version={rv_href}"
        elif self.count_type == self.REMOVED:
            partial_url_str = "{base}?repository_version_removed={rv_href}"
        full_url = partial_url_str.format(
            base=ctype_url, rv_href=rv_href)
        return full_url
