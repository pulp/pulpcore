"""
Repository related Django models.
"""
from contextlib import suppress
from gettext import gettext as _
from os import path
from collections import defaultdict
import logging

import django
from asyncio_throttle import Throttler
from dynaconf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django_lifecycle import AFTER_UPDATE, BEFORE_DELETE, hook
from rest_framework.exceptions import APIException

from pulpcore.app.util import batch_qs, get_view_name_for_model
from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.download.factory import DownloaderFactory
from pulpcore.exceptions import ResourceImmutableError

from pulpcore.cache import Cache

from .base import MasterModel, BaseModel
from .content import Artifact, Content
from .fields import EncryptedTextField
from .task import CreatedResource, Task


_logger = logging.getLogger(__name__)


class Repository(MasterModel):
    """
    Collection of content.

    Fields:

        name (models.TextField): The repository name.
        description (models.TextField): An optional description.
        next_version (models.PositiveIntegerField): A record of the next version number to be
            created.
        retain_repo_versions (models.PositiveIntegerField): Number of repo versions to keep
        user_hidden (models.BooleanField): Whether to expose this repo to users via the API

    Relations:

        content (models.ManyToManyField): Associated content.
        remote (models.ForeignKeyField): Associated remote
    """

    TYPE = "repository"
    CONTENT_TYPES = []
    REMOTE_TYPES = []

    name = models.TextField(db_index=True, unique=True)
    description = models.TextField(null=True)
    next_version = models.PositiveIntegerField(default=0)
    retain_repo_versions = models.PositiveIntegerField(default=None, null=True)
    user_hidden = models.BooleanField(default=False)
    content = models.ManyToManyField(
        "Content", through="RepositoryContent", related_name="repositories"
    )
    remote = models.ForeignKey("Remote", null=True, on_delete=models.SET_NULL)

    class Meta:
        verbose_name_plural = "repositories"

    def on_new_version(self, version):
        """Called after a new repository version has been created.

        Subclasses are expected to override this to do useful things.

        Args:
            version: The new repository version.
        """
        pass

    def save(self, *args, **kwargs):
        """
        Saves Repository model and creates an initial repository version.

        Args:
            args (list): list of positional arguments for Model.save()
            kwargs (dict): dictionary of keyword arguments to pass to Model.save()
        """
        with transaction.atomic():
            adding = self._state.adding
            super().save(*args, **kwargs)
            if adding:
                self.create_initial_version()

    def create_initial_version(self):
        """
        Create an initial repository version (version 0).

        This method can be overriden by plugins if they require custom logic.
        """
        version = RepositoryVersion(repository=self, number=self.next_version, complete=True)
        self.next_version += 1
        self.save()
        version.save()

    def new_version(self, base_version=None):
        """
        Create a new RepositoryVersion for this Repository

        Creation of a RepositoryVersion should be done in a RQ Job.

        Args:
            repository (pulpcore.app.models.Repository): to create a new version of
            base_version (pulpcore.app.models.RepositoryVersion): an optional repository version
                whose content will be used as the set of content for the new version

        Returns:
            pulpcore.app.models.RepositoryVersion: The Created RepositoryVersion
        """
        with transaction.atomic():
            latest_version = self.versions.latest()
            if not latest_version.complete:
                latest_version.delete()

            version = RepositoryVersion(
                repository=self, number=int(self.next_version), base_version=base_version
            )
            version.save()

            if base_version:
                # first remove the content that isn't in the base version
                version.remove_content(version.content.exclude(pk__in=base_version.content))
                # now add any content that's in the base_version but not in version
                version.add_content(base_version.content.exclude(pk__in=version.content))

            if Task.current() and not self.user_hidden:
                resource = CreatedResource(content_object=version)
                resource.save()

            self.invalidate_cache()

            return version

    def finalize_new_version(self, new_version):
        """
        Finalize the incomplete RepositoryVersion with plugin-provided code.

        This method should be overridden by plugin writers for an opportunity for plugin input. This
        method is intended to be called with the incomplete
        :class:`pulpcore.app.models.RepositoryVersion` to validate or modify the content.

        This method does not adjust the value of complete, or save the `RepositoryVersion` itself.
        Its intent is to allow the plugin writer an opportunity for plugin input before pulpcore
        marks the `RepositoryVersion` as complete.

        Args:
            new_version (pulpcore.app.models.RepositoryVersion): The incomplete RepositoryVersion to
                finalize.

        Returns:

        """
        pass

    def latest_version(self):
        """
        Get the latest RepositoryVersion on a repository

        Args:
            repository (pulpcore.app.models.Repository): to get the latest version of

        Returns:
            pulpcore.app.models.RepositoryVersion: The latest RepositoryVersion

        """
        with suppress(RepositoryVersion.DoesNotExist):
            model = self.versions.complete().latest()
            return model

    def natural_key(self):
        """
        Get the model's natural key.

        :return: The model's natural key.
        :rtype: tuple
        """
        return (self.name,)

    @staticmethod
    def artifacts_for_version(version):
        """
        Return the artifacts for a repository version.

        Provides a method that plugins can override since RepositoryVersions aren't typed.

        Args:
            version (pulpcore.app.models.RepositoryVersion): to get the artifacts for

        Returns:
            django.db.models.QuerySet: The artifacts that are contained within this version.
        """
        return Artifact.objects.filter(content__pk__in=version.content)

    @hook(AFTER_UPDATE, when="retain_repo_versions", has_changed=True)
    def _cleanup_old_versions_hook(self):
        # Do not attempt to clean up anything, while there is a transaction involving repo versions
        # still in flight.
        transaction.on_commit(self.cleanup_old_versions)

    def cleanup_old_versions(self):
        """Cleanup old repository versions based on retain_repo_versions."""
        # I am still curious how, but it was reported that this state can happen in day to day
        # operations but its easy to reproduce manually in the pulpcore shell:
        # https://github.com/pulp/pulpcore/issues/2268
        if self.versions.filter(complete=False).exists():
            raise RuntimeError(
                _("Attempt to cleanup old versions, while a new version is in flight.")
            )
        if self.retain_repo_versions:
            # Consider only completed versions for cleanup
            for version in self.versions.complete().order_by("-number")[
                self.retain_repo_versions :
            ]:
                _logger.info(
                    _("Deleting repository version {} due to version retention limit.").format(
                        version
                    )
                )
                version.delete()

    @hook(BEFORE_DELETE)
    def invalidate_cache(self):
        """Invalidates the cache if repository is present."""
        if settings.CACHE_ENABLED:
            distributions = self.distributions.all()
            if distributions.exists():
                base_paths = distributions.values_list("base_path", flat=True)
                if base_paths:
                    Cache().delete(base_key=base_paths)
                # Could do preloading here for immediate artifacts with artifacts_for_version


class Remote(MasterModel):
    """
    A remote source for content.

    This is meant to be subclassed by plugin authors as an opportunity to provide plugin-specific
    persistent data attributes for a plugin remote subclass.

    This object is a Django model that inherits from :class: `pulpcore.app.models.Remote` which
    provides the platform persistent attributes for a remote object. Plugin authors can add
    additional persistent remote data by subclassing this object and adding Django fields. We
    defer to the Django docs on extending this model definition with additional fields.

    Validation of the remote is done at the API level by a plugin defined subclass of
    :class: `pulpcore.plugin.serializers.repository.RemoteSerializer`.

    Fields:

        name (models.TextField): The remote name.
        url (models.TextField): The URL of an external content source.
        ca_cert (models.TextField): A PEM encoded CA certificate used to validate the
            server certificate presented by the external source.
        client_cert (models.TextField): A PEM encoded client certificate used
            for authentication.
        client_key (models.TextField): A PEM encoded private key used for authentication.
        tls_validation (models.BooleanField): If True, TLS peer validation must be performed.
        proxy_url (models.TextField): The optional proxy URL.
            Format: scheme://host:port
        proxy_username (models.TextField): The optional username to authenticate with the proxy.
        proxy_password (models.TextField): The optional password to authenticate with the proxy.
        username (models.TextField): The username to be used for authentication when syncing.
        password (models.TextField): The password to be used for authentication when syncing.
        download_concurrency (models.PositiveIntegerField): Total number of
            simultaneous connections allowed to any remote during a sync.
        policy (models.TextField): The policy to use when downloading content.
        total_timeout (models.FloatField): Value for aiohttp.ClientTimeout.total on connections
        connect_timeout (models.FloatField): Value for aiohttp.ClientTimeout.connect
        sock_connect_timeout (models.FloatField): Value for aiohttp.ClientTimeout.sock_connect
        sock_read_timeout (models.FloatField): Value for aiohttp.ClientTimeout.sock_read
        headers (models.JSONField): Headers set on the aiohttp.ClientSession
        rate_limit (models.IntegerField): Limits total download rate in requests per second.
    """

    TYPE = "remote"

    # Constants for the ChoiceField 'policy'
    IMMEDIATE = "immediate"
    ON_DEMAND = "on_demand"
    STREAMED = "streamed"

    DEFAULT_DOWNLOAD_CONCURRENCY = 10
    DEFAULT_MAX_RETRIES = 3

    POLICY_CHOICES = (
        (IMMEDIATE, "When syncing, download all metadata and content now."),
        (
            ON_DEMAND,
            "When syncing, download metadata, but do not download content now. Instead, "
            "download content as clients request it, and save it in Pulp to be served for "
            "future client requests.",
        ),
        (
            STREAMED,
            "When syncing, download metadata, but do not download content now. Instead,"
            "download content as clients request it, but never save it in Pulp. This causes "
            "future requests for that same content to have to be downloaded again.",
        ),
    )

    name = models.TextField(db_index=True, unique=True)

    url = models.TextField()

    ca_cert = models.TextField(null=True)
    client_cert = models.TextField(null=True)
    client_key = EncryptedTextField(null=True)
    tls_validation = models.BooleanField(default=True)

    username = EncryptedTextField(null=True)
    password = EncryptedTextField(null=True)

    proxy_url = models.TextField(null=True)
    proxy_username = EncryptedTextField(null=True)
    proxy_password = EncryptedTextField(null=True)

    download_concurrency = models.PositiveIntegerField(
        null=True, validators=[MinValueValidator(1, "Download concurrency must be at least 1")]
    )
    max_retries = models.PositiveIntegerField(null=True)
    policy = models.TextField(choices=POLICY_CHOICES, default=IMMEDIATE)

    total_timeout = models.FloatField(
        null=True, validators=[MinValueValidator(0.0, "Timeout must be >= 0")]
    )
    connect_timeout = models.FloatField(
        null=True, validators=[MinValueValidator(0.0, "Timeout must be >= 0")]
    )
    sock_connect_timeout = models.FloatField(
        null=True, validators=[MinValueValidator(0.0, "Timeout must be >= 0")]
    )
    sock_read_timeout = models.FloatField(
        null=True, validators=[MinValueValidator(0.0, "Timeout must be >= 0")]
    )
    headers = models.JSONField(blank=True, null=True)
    rate_limit = models.IntegerField(null=True)

    @property
    def download_factory(self):
        """
        Return the DownloaderFactory which can be used to generate asyncio capable downloaders.

        Upon first access, the DownloaderFactory is instantiated and saved internally.

        Plugin writers are expected to override when additional configuration of the
        DownloaderFactory is needed.

        Returns:
            DownloadFactory: The instantiated DownloaderFactory to be used by
                get_downloader().
        """
        try:
            return self._download_factory
        except AttributeError:
            self._download_factory = DownloaderFactory(self)
            return self._download_factory

    @property
    def download_throttler(self):
        """
        Return the Throttler which can be used to rate limit downloaders.

        Upon first access, the Throttler is instantiated and saved internally.
        Plugin writers are expected to override when additional configuration of the
        DownloaderFactory is needed.

        Returns:
            Throttler: The instantiated Throttler to be used by get_downloader()

        """
        try:
            return self._download_throttler
        except AttributeError:
            if self.rate_limit:
                self._download_throttler = Throttler(rate_limit=self.rate_limit)
                return self._download_throttler

    def get_downloader(self, remote_artifact=None, url=None, **kwargs):
        """
        Get a downloader from either a RemoteArtifact or URL that is configured with this Remote.

        This method accepts either `remote_artifact` or `url` but not both. At least one is
        required. If neither or both are passed a ValueError is raised.

        Plugin writers are expected to override when additional configuration is needed or when
        another class of download is required.

        Args:
            remote_artifact (:class:`~pulpcore.app.models.RemoteArtifact`): The RemoteArtifact to
                download.
            url (str): The URL to download.
            kwargs (dict): This accepts the parameters of
                :class:`~pulpcore.plugin.download.BaseDownloader`.

        Raises:
            ValueError: If neither remote_artifact and url are passed, or if both are passed.

        Returns:
            subclass of :class:`~pulpcore.plugin.download.BaseDownloader`: A downloader that
            is configured with the remote settings.
        """
        if remote_artifact and url:
            raise ValueError(_("get_downloader() cannot accept both 'remote_artifact' and 'url'."))
        if remote_artifact is None and url is None:
            raise ValueError(_("get_downloader() requires either 'remote_artifact' and 'url'."))
        if remote_artifact:
            url = remote_artifact.url
            expected_digests = {}
            for digest_name in ALL_KNOWN_CONTENT_CHECKSUMS:
                digest_value = getattr(remote_artifact, digest_name)
                if digest_value:
                    expected_digests[digest_name] = digest_value
            if expected_digests:
                kwargs["expected_digests"] = expected_digests
            if remote_artifact.size:
                kwargs["expected_size"] = remote_artifact.size
        return self.download_factory.build(url, **kwargs)

    def get_remote_artifact_url(self, relative_path=None):
        """
        Get the full URL for a RemoteArtifact from a relative path.

        This method returns the URL for a RemoteArtifact by concatinating the Remote's url and the
        relative path.located in the Remote. Plugin writers are expected to override this method
        when a more complex algorithm is needed to determine the full URL.

        Args:
            relative_path (str): The relative path of a RemoteArtifact

        Raises:
            ValueError: If relative_path starts with a '/'.

        Returns:
            str: A URL for a RemoteArtifact available at the Remote.
        """
        if path.isabs(relative_path):
            raise ValueError(_("Relative path can't start with '/'. {0}").format(relative_path))
        return path.join(self.url, relative_path)

    def get_remote_artifact_content_type(self, relative_path=None):
        """
        Get the type of content that should be available at the relative path.

        Plugin writers are expected to implement this method.

        Args:
            relative_path (str): The relative path of a RemoteArtifact

        Returns:
            Class: The Class of the content type that should be available at the relative path.
        """
        raise NotImplementedError()

    @hook(BEFORE_DELETE)
    def invalidate_cache(self):
        """Invalidates the cache if remote is present."""
        if settings.CACHE_ENABLED:
            base_paths = self.distribution_set.values_list("base_path", flat=True)
            if base_paths:
                Cache().delete(base_key=base_paths)

    class Meta:
        default_related_name = "remotes"


class RepositoryContent(BaseModel):
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

    content = models.ForeignKey(
        "Content", on_delete=models.CASCADE, related_name="version_memberships"
    )
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    version_added = models.ForeignKey(
        "RepositoryVersion", related_name="added_memberships", on_delete=models.CASCADE
    )
    version_removed = models.ForeignKey(
        "RepositoryVersion", null=True, related_name="removed_memberships", on_delete=models.CASCADE
    )

    class Meta:
        unique_together = (
            ("repository", "content", "version_added"),
            ("repository", "content", "version_removed"),
        )


class RepositoryVersionQuerySet(models.QuerySet):
    """A queryset that provides repository version filtering methods."""

    def complete(self):
        return self.filter(complete=True)

    def with_content(self, content):
        """
        Filters repository versions that contain the provided content units.

        Args:
            content (django.db.models.QuerySet): query of content

        Returns:
            django.db.models.QuerySet: Repository versions which contains content.
        """
        query = models.Q(pk__in=[])
        repo_content = RepositoryContent.objects.filter(content__pk__in=content)

        for rc in repo_content.iterator():
            filter = models.Q(
                repository__pk=rc.repository.pk,
                number__gte=rc.version_added.number,
            )
            if rc.version_removed:
                filter &= models.Q(number__lt=rc.version_removed.number)

            query |= filter

        return self.filter(query)


class RepositoryVersion(BaseModel):
    """
    A version of a repository's content set.

    Plugin Writers are strongly encouraged to use RepositoryVersion as a context manager to provide
    transactional safety, working directory set up, plugin finalization, and cleaning up the
    database on failures.

    Examples::

        with repository.new_version(repository) as new_version:
            new_version.add_content(content_q)
            new_version.remove_content(content_q)

    Fields:

        number (models.PositiveIntegerField): A positive integer that uniquely identifies a version
            of a specific repository. Each new version for a repo should have this field set to
            1 + the most recent version.
        complete (models.BooleanField): If true, the RepositoryVersion is visible. This field is set
            to true when the task that creates the RepositoryVersion is complete.

    Relations:

        repository (models.ForeignKey): The associated repository.
        base_version (models.ForeignKey): The repository version this was created from.
    """

    objects = RepositoryVersionQuerySet.as_manager()

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(db_index=True)
    complete = models.BooleanField(db_index=True, default=False)
    base_version = models.ForeignKey("RepositoryVersion", null=True, on_delete=models.SET_NULL)

    class Meta:
        default_related_name = "versions"
        unique_together = ("repository", "number")
        get_latest_by = "number"
        ordering = ("number",)

    def _content_relationships(self):
        """
        Returns a set of repository_content for a repository version

        Returns:
            django.db.models.QuerySet: The repository_content that is contained within this version.
        """
        return RepositoryContent.objects.filter(
            repository=self.repository, version_added__number__lte=self.number
        ).exclude(version_removed__number__lte=self.number)

    def get_content(self, content_qs=None):
        """
        Returns a set of content for a repository version

        Args:
            content_qs (:class:`django.db.models.QuerySet`): The queryset for Content that will be
                restricted further to the content present in this repository version. If not given,
                ``Content.objects.all()`` is used (to return over all content types present in the
                repository version).

        Returns:
            django.db.models.QuerySet: The content that is contained within this version.

        Examples:
            >>> repository_version = ...
            >>>
            >>> # Return a queryset of File objects in the repository
            >>> repository_version.get_content(content_qs=File.objects)):
        """

        if content_qs is None:
            content_qs = Content.objects

        return content_qs.filter(version_memberships__in=self._content_relationships())

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

        return self.get_content()

    def content_batch_qs(self, content_qs=None, order_by_params=("pk",), batch_size=1000):
        """
        Generate content batches to efficiently iterate over all content.

        Generates query sets that span the `content_qs` content of the repository
        version. Each yielded query set evaluates to at most `batch_size` content records.
        This is useful to limit the memory footprint when iterating over all content of
        a repository version.

        .. note::

            * This generator is not safe against changes (i.e. add/remove content) during
              the iteration!

            * As the method uses slices internally, the queryset must be ordered to yield
              stable results. By default, it is ordered by primary key.

        Args:
            content_qs (:class:`django.db.models.QuerySet`): The queryset for Content that will be
                restricted further to the content present in this repository version. If not given,
                ``Content.objects.all()`` is used (to iterate over all content present in the
                repository version). A plugin may want to use a specific subclass of
                :class:`~pulpcore.plugin.models.Content` or use e.g. ``filter()`` to select
                a subset of the repository version's content.
            order_by_params (tuple of str): The parameters for the ``order_by`` clause
                for the content. The Default is ``("pk",)``. This needs to
                specify a stable order. For example, if you want to iterate by
                decreasing creation time stamps use ``("-pulp_created", "pk")`` to
                ensure that content records are still sorted by primary key even
                if their creation timestamp happens to be equal.
            batch_size (int): The maximum batch size.

        Yields:
            :class:`django.db.models.QuerySet`: A QuerySet representing a slice of the content.

        Example:
            The following code could be used to loop over all ``FileContent`` in
            ``repository_version``. It prefetches the related
            :class:`~pulpcore.plugin.models.ContentArtifact` instances for every batch::

                repository_version = ...

                batch_generator = repository_version.content_batch_qs(
                    content_class=FileContent.objects.all()
                )
                for content_batch_qs in batch_generator:
                    content_batch_qs.prefetch_related("contentartifact_set")
                    for content in content_batch_qs:
                        ...

        """
        version_content_qs = self.get_content(content_qs).order_by(*order_by_params)
        yield from batch_qs(version_content_qs, batch_size=batch_size)

    @property
    def artifacts(self):
        """
        Returns a set of artifacts for a repository version.

        Returns:
            django.db.models.QuerySet: The artifacts that are contained within this version.
        """
        return self.repository.cast().artifacts_for_version(self)

    def added(self, base_version=None):
        """
        Args:
            base_version (pulpcore.app.models.RepositoryVersion): an optional repository version

        Returns:
            QuerySet: The Content objects that were added by this version.
        """
        if not base_version:
            return Content.objects.filter(version_memberships__version_added=self)

        return Content.objects.filter(
            version_memberships__in=self._content_relationships()
        ).exclude(version_memberships__in=base_version._content_relationships())

    def removed(self, base_version=None):
        """
        Args:
            base_version (pulpcore.app.models.RepositoryVersion): an optional repository version

        Returns:
            QuerySet: The Content objects that were removed by this version.
        """
        if not base_version:
            return Content.objects.filter(version_memberships__version_removed=self)

        return Content.objects.filter(
            version_memberships__in=base_version._content_relationships()
        ).exclude(version_memberships__in=self._content_relationships())

    def contains(self, content):
        """
        Check whether a content exists in this repository version's set of content

        Returns:
            bool: True if the repository version contains the content, False otherwise
        """
        return self.content.filter(pk=content.pk).exists()

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
        to_add = set(content.exclude(pk__in=self.content).values_list("pk", flat=True))

        # Normalize representation if content has already been removed in this version and
        # is re-added: Undo removal by setting version_removed to None.
        for removed in batch_qs(self.removed().order_by("pk").values_list("pk", flat=True)):
            to_readd = to_add.intersection(set(removed))
            if to_readd:
                RepositoryContent.objects.filter(
                    content__in=to_readd, repository=self.repository, version_removed=self
                ).update(version_removed=None)
                to_add = to_add - to_readd

        for content_pk in to_add:
            repo_content.append(
                RepositoryContent(
                    repository=self.repository, content_id=content_pk, version_added=self
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

        if not content or not content.count():
            return

        # Normalize representation if content has already been added in this version.
        # Undo addition by deleting the RepositoryContent.
        RepositoryContent.objects.filter(
            repository=self.repository,
            content_id__in=content,
            version_added=self,
            version_removed=None,
        ).delete()

        q_set = RepositoryContent.objects.filter(
            repository=self.repository, content_id__in=content, version_removed=None
        )
        q_set.update(version_removed=self)

    def set_content(self, content):
        """
        Sets the repo version content by calling remove_content() then add_content().

        Args:
            content (django.db.models.QuerySet): Set of desired content

        Raise:
            pulpcore.exception.ResourceImmutableError: if set_content is called on a
                complete RepositoryVersion
        """
        self.remove_content(self.content.exclude(pk__in=content))
        self.add_content(content.exclude(pk__in=self.content))

    def next(self):
        """
        Returns:
            pulpcore.app.models.RepositoryVersion: The next complete RepositoryVersion for the same
                repository.
        Raises:
            RepositoryVersion.DoesNotExist: if there is not a RepositoryVersion for the same
                repository and with a higher "number".
        """
        try:
            return (
                self.repository.versions.complete()
                .filter(number__gt=self.number)
                .order_by("number")[0]
            )
        except IndexError:
            raise self.DoesNotExist

    def previous(self):
        """
        Returns:
            pulpcore.app.models.RepositoryVersion: The previous complete RepositoryVersion for the
                same repository.

        Raises:
            RepositoryVersion.DoesNotExist: if there is not a RepositoryVersion for the same
                repository and with a lower "number".
        """
        try:
            return (
                self.repository.versions.complete()
                .filter(number__lt=self.number)
                .order_by("-number")[0]
            )
        except IndexError:
            raise self.DoesNotExist

    def _squash(self, repo_relations, next_version):
        """
        Squash a complete repo version into the next version
        """
        # delete any relationships added in the version being deleted and removed in the next one.
        repo_relations.filter(version_added=self, version_removed=next_version).delete()

        # If the same content is deleted in version, but added back in next_version then:
        # - set version_removed field in relation to version_removed of the relation adding
        #   the content in next version because the content can be removed again after the
        #   next_version
        # - and remove relation adding the content in next_version
        content_added = repo_relations.filter(version_added=next_version).values_list("content_id")

        # use list() to force the evaluation of the queryset, otherwise queryset is affected
        # by the update() operation before delete() is ran
        content_removed_and_readded = list(
            repo_relations.filter(version_removed=self, content_id__in=content_added).values_list(
                "content_id"
            )
        )

        repo_contents_readded_in_next_version = repo_relations.filter(
            version_added=next_version, content_id__in=content_removed_and_readded
        )

        # Since the readded contents can be removed again by any subsequent version after the
        # next version. Get the mapping of readded contents and their versions removed to use
        # later. The version removed id will be None if a content is not removed.
        version_removed_id_content_id_map = defaultdict(list)
        for readded_repo_content in repo_contents_readded_in_next_version.iterator():
            version_removed_id_content_id_map[readded_repo_content.version_removed_id].append(
                readded_repo_content.content_id
            )

        repo_contents_readded_in_next_version.delete()

        # Update the version removed of the readded contents
        for version_removed_id, content_ids in version_removed_id_content_id_map.items():
            repo_relations.filter(version_removed=self, content_id__in=content_ids).update(
                version_removed_id=version_removed_id
            )

        # "squash" by moving other additions and removals forward to the next version
        repo_relations.filter(version_added=self).update(version_added=next_version)
        repo_relations.filter(version_removed=self).update(version_removed=next_version)

        # Update next version's counts as they have been modified
        next_version._compute_counts()

    def delete(self, **kwargs):
        """
        Deletes a RepositoryVersion

        If RepositoryVersion is complete and has a successor, squash RepositoryContent changes into
        the successor. If version is incomplete, delete and and clean up RepositoryContent,
        CreatedResource, and Repository objects.

        Deletion of a complete RepositoryVersion should be done in a RQ Job.
        """
        if self.complete:
            if self.repository.versions.complete().count() <= 1:
                raise APIException(_("Attempt to delete the last remaining version."))
            if settings.CACHE_ENABLED:
                base_paths = self.distribution_set.values_list("base_path", flat=True)
                if base_paths:
                    Cache().delete(base_key=base_paths)

            # Handle the manipulation of the repository version content and its final deletion in
            # the same transaction.
            with transaction.atomic():
                repo_relations = RepositoryContent.objects.filter(
                    repository=self.repository
                ).select_for_update()
                try:
                    next_version = self.next()
                    self._squash(repo_relations, next_version)

                except RepositoryVersion.DoesNotExist:
                    # version is the latest version so simply update repo contents
                    # and delete the version
                    repo_relations.filter(version_added=self).delete()
                    repo_relations.filter(version_removed=self).update(version_removed=None)

                if repo_relations.filter(Q(version_added=self) | Q(version_removed=self)).exists():
                    raise RuntimeError(
                        _("Some repo relations of this version were not translated.")
                    )
                super().delete(**kwargs)

        else:
            with transaction.atomic():
                RepositoryContent.objects.filter(version_added=self).delete()
                RepositoryContent.objects.filter(version_removed=self).update(version_removed=None)
                CreatedResource.objects.filter(object_id=self.pk).delete()
                super().delete(**kwargs)

    def _compute_counts(self):
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
                annotated = qs.values("pulp_type").annotate(count=models.Count("pulp_type"))
                for item in annotated:
                    count_obj = RepositoryVersionContentDetails(
                        content_type=item["pulp_type"],
                        repository_version=self,
                        count=item["count"],
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
        if self.complete:
            raise RuntimeError(
                _("This Repository version is complete. It cannot be modified further.")
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Finalize and save the RepositoryVersion if no errors are raised, delete it if not
        """
        if exc_value:
            self.delete()
        else:
            try:
                repository = self.repository.cast()
                repository.finalize_new_version(self)
                no_change = not self.added() and not self.removed()
                if no_change:
                    self.delete()
                else:
                    content_types_seen = set(
                        self.content.values_list("pulp_type", flat=True).distinct()
                    )
                    content_types_supported = set(
                        ctype.get_pulp_type() for ctype in repository.CONTENT_TYPES
                    )

                    unsupported_types = content_types_seen - content_types_supported
                    if unsupported_types:
                        raise ValueError(
                            _("Saw unsupported content types {}").format(unsupported_types)
                        )

                    self.complete = True
                    self.repository.next_version = self.number + 1
                    with transaction.atomic():
                        self.repository.save()
                        self.save()
                        self._compute_counts()
                    self.repository.cleanup_old_versions()
                    repository.on_new_version(self)
            except Exception:
                self.delete()
                raise

    def __str__(self):
        return "<Repository: {}; Version: {}>".format(self.repository.name, self.number)


class RepositoryVersionContentDetails(models.Model):
    ADDED = "A"
    PRESENT = "P"
    REMOVED = "R"
    COUNT_TYPE_CHOICES = (
        (ADDED, "added"),
        (PRESENT, "present"),
        (REMOVED, "removed"),
    )

    count_type = models.CharField(max_length=1, choices=COUNT_TYPE_CHOICES)
    content_type = models.TextField()
    repository_version = models.ForeignKey(
        "RepositoryVersion", related_name="counts", on_delete=models.CASCADE
    )
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
            dict: {<pulp_type>: <url>}
        """
        ctype_model = Content.objects.filter(pulp_type=self.content_type).first().cast().__class__
        ctype_view = get_view_name_for_model(ctype_model, "list")
        try:
            ctype_url = reverse(ctype_view)
        except django.urls.exceptions.NoReverseMatch:
            # We've hit a content type for which there is no viewset.
            # There's nothing we can do here, except to skip it.
            return
        repository = self.repository_version.repository.cast()
        repository_view = get_view_name_for_model(repository.__class__, "list")

        repository_url = reverse(repository_view)
        rv_href = (
            repository_url
            + str(repository.pk)
            + "/versions/{version}/".format(version=self.repository_version.number)
        )
        if self.count_type == self.ADDED:
            partial_url_str = "{base}?repository_version_added={rv_href}"
        elif self.count_type == self.PRESENT:
            partial_url_str = "{base}?repository_version={rv_href}"
        elif self.count_type == self.REMOVED:
            partial_url_str = "{base}?repository_version_removed={rv_href}"
        full_url = partial_url_str.format(base=ctype_url, rv_href=rv_href)
        return full_url
