"""
Content related Django models.
"""

from gettext import gettext as _

import asyncio
import datetime
import json
import tempfile
import shutil
import subprocess

from collections import defaultdict
from functools import lru_cache, partial
from itertools import chain

from django.conf import settings
from django.core import validators
from django.db import IntegrityError, models, transaction
from django.forms.models import model_to_dict
from django.utils.timezone import now
from django_guid import get_guid
from django_lifecycle import BEFORE_UPDATE, BEFORE_SAVE, hook

from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.app import pulp_hashlib
from pulpcore.app.util import gpg_verify, get_domain_pk
from pulpcore.app.models import MasterModel, BaseModel, fields, storage
from pulpcore.exceptions import (
    DigestValidationError,
    SizeValidationError,
    MissingDigestValidationError,
    UnsupportedDigestValidationError,
)

# All available digest fields ordered by algorithm strength.
_DIGEST_FIELDS = []
for alg in ("sha512", "sha384", "sha256", "sha224", "sha1", "md5"):
    if alg in settings.ALLOWED_CONTENT_CHECKSUMS:
        _DIGEST_FIELDS.append(alg)

# All available digest fields ordered by relative frequency
# (Better average-case performance in some algorithms with fallback)
_COMMON_DIGEST_FIELDS = []
for alg in ("sha256", "sha512", "sha384", "sha224", "sha1", "md5"):
    if alg in settings.ALLOWED_CONTENT_CHECKSUMS:
        _COMMON_DIGEST_FIELDS.append(alg)

# Available, reliable digest fields ordered by algorithm strength.
_RELIABLE_DIGEST_FIELDS = []
for alg in ("sha512", "sha384", "sha256"):
    if alg in settings.ALLOWED_CONTENT_CHECKSUMS:
        _RELIABLE_DIGEST_FIELDS.append(alg)

# Digest-fields that are NOT ALLOWED
_FORBIDDEN_DIGESTS = set(ALL_KNOWN_CONTENT_CHECKSUMS).difference(settings.ALLOWED_CONTENT_CHECKSUMS)


class BulkCreateManager(models.Manager):
    """
    A manager that provides a bulk_get_or_create()
    """

    def bulk_get_or_create(self, objs, batch_size=None):
        """
        Insert the list of objects into the database and get existing objects from the database.

        Do *not* call save() on each of the instances, do not send any pre/post_save signals,
        and do not set the primary key attribute if it is an autoincrement field (except if
        features.can_return_ids_from_bulk_insert=True). Multi-table models are not supported.

        If an IntegrityError is raised while performing a bulk insert, this method falls back to
        inserting each instance individually. The already-existing instances are retrieved from
        the database and returned with the other newly created instances.

        Args:
            objs (iterable of models.Model): an iterable of Django Model instances
            batch_size (int): how many are created in a single query

        Returns:
            List of instances that were inserted into the database.
        """

        objs = list(objs)
        try:
            with transaction.atomic():
                return super().bulk_create(objs, batch_size=batch_size)
        except IntegrityError:
            for i in range(len(objs)):
                try:
                    with transaction.atomic():
                        objs[i].save()
                except IntegrityError:
                    objs[i] = objs[i].__class__.objects.get(objs[i].q())
        return objs


class BulkTouchQuerySet(models.QuerySet):
    """
    A query set that provides ``touch()``.
    """

    def touch(self):
        """
        Update the ``timestamp_of_interest`` on all objects of the query.

        Postgres' UPDATE call doesn't support order-by. This can (and does) result in deadlocks in
        high-concurrency environments, when using touch() on overlapping data sets. In order to
        prevent this, we choose to SELECT FOR UPDATE with SKIP LOCKS == True, and only update
        the rows that we were able to get locks on. Since a previously-locked-row implies
        that updating that row's timestamp-of-interest is the responsibility of whoever currently
        owns it, this results in correct data, while closing the window on deadlocks.
        """
        with transaction.atomic():
            sub_q = self.order_by("pk").select_for_update(skip_locked=True)
            return self.filter(pk__in=sub_q).update(timestamp_of_interest=now())


class QueryMixin:
    """
    A mixin that provides models with querying utilities.
    """

    def q(self):
        """
        Returns a Q object that represents the model
        """
        if not self._state.adding:
            return models.Q(pk=self.pk)
        try:
            kwargs = self.natural_key_dict()
        except AttributeError:
            all_kwargs = model_to_dict(self)
            kwargs = {k: v for k, v in all_kwargs.items() if v}
        return models.Q(**kwargs)


class HandleTempFilesMixin:
    """
    A mixin that provides methods for handling temporary files.
    """

    def save(self, *args, **kwargs):
        """
        Saves Model and closes the file associated with the Model

        Args:
            args (list): list of positional arguments for Model.save()
            kwargs (dict): dictionary of keyword arguments to pass to Model.save()
        """
        try:
            super().save(*args, **kwargs)
        finally:
            self.file.close()

    def delete(self, *args, **kwargs):
        """
        Deletes Model and the file associated with the Model

        Args:
            args (list): list of positional arguments for Model.delete()
            kwargs (dict): dictionary of keyword arguments to pass to Model.delete()
        """
        super().delete(*args, **kwargs)
        # In case of rollback, we want the artifact to stay connected with it's file.
        transaction.on_commit(partial(self.file.delete, save=False))


class ArtifactQuerySet(BulkTouchQuerySet):
    def orphaned(self, orphan_protection_time):
        """Returns set of orphaned artifacts that are ready to be cleaned up."""
        domain_pk = get_domain_pk()
        expiration = now() - datetime.timedelta(minutes=orphan_protection_time)
        return self.filter(
            content_memberships__isnull=True,
            timestamp_of_interest__lt=expiration,
            pulp_domain=domain_pk,
        )


class Artifact(HandleTempFilesMixin, BaseModel):
    """
    A file associated with a piece of content.

    When calling `save()` on an Artifact, if the file is not stored in Django's storage backend, it
    is moved into place then.

    Artifact is compatible with Django's `bulk_create()` method.

    Fields:

        file (pulpcore.app.models.fields.ArtifactFileField): The stored file. This field should
            be set using an absolute path to a temporary file.
            It also accepts `class:django.core.files.File`.
        size (models.BigIntegerField): The size of the file in bytes.
        md5 (models.CharField): The MD5 checksum of the file.
        sha1 (models.CharField): The SHA-1 checksum of the file.
        sha224 (models.CharField): The SHA-224 checksum of the file.
        sha256 (models.CharField): The SHA-256 checksum of the file (REQUIRED).
        sha384 (models.CharField): The SHA-384 checksum of the file.
        sha512 (models.CharField): The SHA-512 checksum of the file.
        timestamp_of_interest (models.DateTimeField): timestamp that prevents orphan cleanup.
        pulp_domain (models.ForeignKey): The domain the artifact is a part of.
    """

    def storage_path(self, name):
        """
        Callable used by FileField to determine where the uploaded file should be stored.

        Args:
            name (str): Original name of uploaded file. It is ignored by this method because the
                sha256 checksum is used to determine a file path instead.
        """
        return storage.get_artifact_path(self.sha256)

    file = fields.ArtifactFileField(
        null=False, upload_to=storage_path, storage=storage.DomainStorage, max_length=255
    )
    size = models.BigIntegerField(null=False)
    md5 = models.CharField(max_length=32, null=True, unique=False, db_index=True)
    sha1 = models.CharField(max_length=40, null=True, unique=False, db_index=True)
    sha224 = models.CharField(max_length=56, null=True, unique=False, db_index=True)
    sha256 = models.CharField(max_length=64, null=False, db_index=True)
    sha384 = models.CharField(max_length=96, null=True, db_index=True)
    sha512 = models.CharField(max_length=128, null=True, db_index=True)
    timestamp_of_interest = models.DateTimeField(auto_now=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    objects = BulkCreateManager.from_queryset(ArtifactQuerySet)()

    # All available digest fields ordered by algorithm strength.
    DIGEST_FIELDS = _DIGEST_FIELDS

    # All available digest fields ordered by relative frequency
    # (Better average-case performance in some algorithms with fallback)
    COMMON_DIGEST_FIELDS = _COMMON_DIGEST_FIELDS

    # Available, reliable digest fields ordered by algorithm strength.
    RELIABLE_DIGEST_FIELDS = _RELIABLE_DIGEST_FIELDS

    # Digest-fields that are NOT ALLOWED
    FORBIDDEN_DIGESTS = _FORBIDDEN_DIGESTS

    class Meta:
        unique_together = (
            ("sha256", "pulp_domain"),
            ("sha384", "pulp_domain"),
            ("sha512", "pulp_domain"),
        )

    @hook(BEFORE_SAVE)
    def before_save(self):
        """
        Pre-save hook that validates checksum rules prior to allowing an Artifact to be saved.

        An Artifact with any checksums from the FORBIDDEN set will fail to save while raising
        an UnsupportedDigestValidationError exception.

        Similarly, any checksums in DIGEST_FIELDS that is NOT set will raise a
        MissingDigestValidationError exception.

        Raises:
            :class: `~pulpcore.exceptions.UnsupportedDigestValidationError`: When any of the
                keys on FORBIDDEN_DIGESTS are set for the Artifact
            :class: `~pulpcore.exceptions.MissingDigestValidationError`: When any of the
                keys on DIGEST_FIELDS are found to be missing from the Artifact
        """
        bad_keys = [k for k in self.FORBIDDEN_DIGESTS if getattr(self, k)]
        if bad_keys:
            raise UnsupportedDigestValidationError(
                _("Checksum algorithms {} are forbidden for this Pulp instance.").format(bad_keys)
            )

        missing_keys = [k for k in self.DIGEST_FIELDS if not getattr(self, k)]
        if missing_keys:
            raise MissingDigestValidationError(
                _("Missing required checksum algorithms {}.").format(missing_keys)
            )

    def q(self):
        if not self._state.adding:
            return models.Q(pk=self.pk)
        for digest_name in self.DIGEST_FIELDS:
            digest_value = getattr(self, digest_name)
            if digest_value:
                return models.Q(**{digest_name: digest_value}, pulp_domain=self.pulp_domain)
        return models.Q()

    def is_equal(self, other):
        """
        Is equal by matching digest.

        Args:
            other (pulpcore.app.models.Artifact): A artifact to match.

        Returns:
            bool: True when equal.
        """
        for field in self.RELIABLE_DIGEST_FIELDS:
            digest = getattr(self, field)
            if not digest:
                continue
            if digest == getattr(other, field):
                return True
        return False

    @staticmethod
    def init_and_validate(file, expected_digests=None, expected_size=None):
        """
        Initialize an in-memory Artifact from a file, and validate digest and size info.

        This accepts both a path to a file on-disk or a
        [pulpcore.app.files.PulpTemporaryUploadedFile][].

        Args:
            file ([pulpcore.app.files.PulpTemporaryUploadedFile][] or str): The
                PulpTemporaryUploadedFile to create the Artifact from or a string with the full path
                to the file on disk.
            expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
                value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
            expected_size (int): The number of bytes the download is expected to have.

        Raises:
            [pulpcore.exceptions.DigestValidationError][]: When any of the ``expected_digest``
                values don't match the digest of the data
            [pulpcore.exceptions.SizeValidationError][]: When the ``expected_size`` value
                doesn't match the size of the data
            [pulpcore.exceptions.UnsupportedDigestValidationError][]: When any of the
                ``expected_digest`` algorithms aren't in the ALLOWED_CONTENT_CHECKSUMS list
        Returns:
            An in-memory, unsaved [pulpcore.plugin.models.Artifact][]
        """
        if isinstance(file, str):
            with open(file, "rb") as f:
                hashers = {n: pulp_hashlib.new(n) for n in Artifact.DIGEST_FIELDS}
                size = 0
                while True:
                    chunk = f.read(1048576)  # 1 megabyte
                    if not chunk:
                        break
                    for algorithm in hashers.values():
                        algorithm.update(chunk)
                    size = size + len(chunk)
        else:
            size = file.size
            hashers = file.hashers

        if expected_size:
            if size != expected_size:
                raise SizeValidationError(size, expected_size)

        if expected_digests:
            for algorithm, expected_digest in expected_digests.items():
                if algorithm not in hashers:
                    raise UnsupportedDigestValidationError(
                        _("Checksum algorithm {} forbidden for this Pulp instance.").format(
                            algorithm
                        )
                    )
                actual_digest = hashers[algorithm].hexdigest()
                if expected_digest != actual_digest:
                    raise DigestValidationError(actual_digest, expected_digest)

        attributes = {"size": size, "file": file}
        for algorithm in Artifact.DIGEST_FIELDS:
            attributes[algorithm] = hashers[algorithm].hexdigest()

        return Artifact(**attributes)

    @classmethod
    def from_pulp_temporary_file(cls, temp_file):
        """
        Creates an Artifact from PulpTemporaryFile.

        Returns:
            An saved [pulpcore.plugin.models.Artifact][]
        """
        artifact_file = temp_file.file.open()
        with tempfile.NamedTemporaryFile("wb") as new_file:
            shutil.copyfileobj(artifact_file, new_file)
            new_file.flush()
            artifact_file.close()
            artifact = cls.init_and_validate(new_file.name)
            artifact.save()
        temp_file.delete()
        return artifact

    def touch(self):
        """Update timestamp_of_interest."""
        self.save(update_fields=["timestamp_of_interest"])


class PulpTemporaryFile(HandleTempFilesMixin, BaseModel):
    """
    A temporary file saved to the storage backend.

    Commonly used to pass data to one or more tasks.

    Fields:

        file (pulpcore.app.models.fields.ArtifactFileField): The stored file. This field should
            be set using an absolute path to a temporary file.
            It also accepts `class:django.core.files.File`.

    Relations:
        pulp_domain (pulpcore.app.models.Domain): The domain this temp file is a part of.
    """

    def storage_path(self, name):
        """
        Callable used by FileField to determine where the uploaded file should be stored.

        Args:
            name (str): Original name of uploaded file. It is ignored by this method because the
                pulp_id is used to determine a file path instead.
        """
        return storage.get_temp_file_path(self.pulp_id)

    file = fields.ArtifactFileField(
        null=False, upload_to=storage_path, storage=storage.DomainStorage, max_length=255
    )
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    @staticmethod
    def init_and_validate(file, expected_digests=None, expected_size=None):
        """
        Initialize an in-memory PulpTemporaryFile from a file, and validate digest and size info.

        This accepts both a path to a file on-disk or a
        [pulpcore.app.files.PulpTemporaryUploadedFile][].

        Args:
            file ([pulpcore.app.files.PulpTemporaryUploadedFile][] or str): The
                PulpTemporaryUploadedFile to create the PulpTemporaryFile from or a string with the
                full path to the file on disk.
            expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
                value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
            expected_size (int): The number of bytes the download is expected to have.

        Raises:
            [pulpcore.exceptions.DigestValidationError][]: When any of the ``expected_digest``
                values don't match the digest of the data
            [pulpcore.exceptions.SizeValidationError][]: When the ``expected_size`` value
                doesn't match the size of the data
            [pulpcore.exceptions.UnsupportedDigestValidationError][]: When any of the
                ``expected_digest`` algorithms aren't in the ALLOWED_CONTENT_CHECKSUMS list

        Returns:
            An in-memory, unsaved [pulpcore.plugin.models.PulpTemporaryFile][]
        """
        if not expected_digests and not expected_size:
            return PulpTemporaryFile(file=file)

        if isinstance(file, str):
            with open(file, "rb") as f:
                hashers = {n: pulp_hashlib.new(n) for n in expected_digests.keys()}
                size = 0
                while True:
                    chunk = f.read(1048576)  # 1 megabyte
                    if not chunk:
                        break
                    for algorithm in hashers.values():
                        algorithm.update(chunk)
                    size = size + len(chunk)
        else:
            size = file.size
            hashers = file.hashers

        if expected_size:
            if size != expected_size:
                raise SizeValidationError(size, expected_size)

        if expected_digests:
            for algorithm, expected_digest in expected_digests.items():
                if algorithm not in hashers:
                    raise UnsupportedDigestValidationError(
                        _("Checksum algorithm {} forbidden for this Pulp instance.").format(
                            algorithm
                        )
                    )
                actual_digest = hashers[algorithm].hexdigest()
                if expected_digest != actual_digest:
                    raise DigestValidationError(actual_digest, expected_digest)

        return PulpTemporaryFile(file=file)


class ContentQuerySet(BulkTouchQuerySet):
    def orphaned(self, orphan_protection_time, content_pks=None):
        """Returns set of orphaned content that is ready to be cleaned up."""
        expiration = now() - datetime.timedelta(minutes=orphan_protection_time)
        if content_pks:
            return self.filter(
                version_memberships__isnull=True,
                timestamp_of_interest__lt=expiration,
                pk__in=content_pks,
            )

        domain_pk = get_domain_pk()
        return self.filter(
            pulp_domain=domain_pk,
            version_memberships__isnull=True,
            timestamp_of_interest__lt=expiration,
        )


ContentManager = BulkCreateManager.from_queryset(ContentQuerySet)


class Content(MasterModel, QueryMixin):
    """
    A piece of managed content.

    Fields:
        upstream_id (models.UUIDField) : identifier of content imported from an 'upstream' Pulp
        timestamp_of_interest (models.DateTimeField): timestamp that prevents orphan cleanup

    Relations:

        _artifacts (models.ManyToManyField): Artifacts related to Content through ContentArtifact
        pulp_domain (models.ForeignKey): Pulp Domain this content lives in
    """

    PROTECTED_FROM_RECLAIM = True
    _repository_types = defaultdict(set)

    TYPE = "content"
    repo_key_fields = ()  # Used by pulpcore.plugin.repo_version_utils.remove_duplicates
    upstream_id = models.UUIDField(null=True)  # Used by PulpImport/Export processing

    _artifacts = models.ManyToManyField(Artifact, through="ContentArtifact")
    timestamp_of_interest = models.DateTimeField(auto_now=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    objects = ContentManager()

    class Meta:
        verbose_name_plural = "content"
        unique_together = ()

    @classmethod
    def repository_types(cls):
        """
        Tuple of the repository models that can store this content type.

        Populated at start up time. Read only.
        """
        return tuple(cls._repository_types[cls])

    @classmethod
    def natural_key_fields(cls):
        """
        Returns a tuple of the natural key fields which usually equates to unique_together fields.

        This can be overwritten in subclasses and should return a tuple of field names.
        """
        return tuple(chain.from_iterable(cls._meta.unique_together))

    @classmethod
    @lru_cache(typed=True)
    def _sanitized_natural_key_fields(cls):
        """
        This function translates the names of the key fields to their attname.

        In case of foreign keys, this decodes to the corresponding `<...>_id` field preventing
        extra DB accesses to fetch the related objects.
        """
        return tuple(getattr(cls, field).field.attname for field in cls.natural_key_fields())

    def natural_key(self):
        """
        Get the model's natural key based on natural_key_fields.

        Returns:
            tuple: The natural key.
        """
        return tuple(getattr(self, f) for f in self._sanitized_natural_key_fields())

    def natural_key_dict(self):
        """
        Get the model's natural key as a dictionary of keys and values.
        """
        return {f: getattr(self, f) for f in self._sanitized_natural_key_fields()}

    @staticmethod
    def init_from_artifact_and_relative_path(artifact, relative_path):
        """
        Return an instance of the specific content by inspecting an artifact.

        Plugin writers are expected to override this method with an implementation for a specific
        content type. If the content type is stored with multiple artifacts plugin writers can
        instead return a tuple of the unsaved content instance and a dictionary of the content's
        artifacts by their relative paths.

        For example::

            if path.isabs(relative_path):
                raise ValueError(_("Relative path can't start with '/'."))
            return FileContent(relative_path=relative_path, digest=artifact.sha256)

        Args:
            artifact (pulpcore.plugin.models.Artifact) An instance of an Artifact
            relative_path (str): Relative path for the content

        Raises:
            ValueError: If relative_path starts with a '/'.

        Returns:
            An un-saved instance of [pulpcore.plugin.models.Content][] sub-class. Or a
            tuple of an un-saved instance of [pulpcore.plugin.models.Content][] and a dict
            of form [relative_path:str, Optional[artifact:`~pulpcore.plugin.models.Artifact`]]
        """
        raise NotImplementedError()

    def touch(self):
        """Update timestamp_of_interest."""
        self.save(update_fields=["timestamp_of_interest"])


class ContentArtifact(BaseModel, QueryMixin):
    """
    A relationship between a Content and an Artifact.

    Serves as a through model for the '_artifacts' ManyToManyField in Content.
    Artifact is protected from deletion if it's present in a ContentArtifact relationship.
    """

    artifact = models.ForeignKey(
        Artifact, on_delete=models.PROTECT, null=True, related_name="content_memberships"
    )
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    relative_path = models.TextField()

    objects = BulkCreateManager()

    class Meta:
        unique_together = ("content", "relative_path")
        indexes = [models.Index(fields=["relative_path"])]

    @staticmethod
    def sort_key(ca):
        """
        Static method for defining a sort-key for a specified ContentArtifact.

        Sorting lists of ContentArtifacts is critical for avoiding deadlocks in high-concurrency
        environments, when multiple workers may be operating on similar sets of content at the
        same time. Providing a stable sort-order becomes problematic when the CAs in question
        haven't been persisted - in that case, pulp_id can't be relied on, as it will change
        when the object is stored in the DB and its "real" key is generated.

        This method produces a key based on the content/artifact represented by the CA.

        Args:
            ca (pulpcore.plugin.models.ContentArtifact) The CA we need a key for

        Returns:
            a tuple of (str(content-key), str(artifact-key)) that can be reliably sorted on
        """
        c_key = ""
        a_key = ""
        # It's possible to only have one of content/artifact - handle that
        if ca.content:
            # Some key-fields aren't str, handle that
            c_key = "".join(map(str, ca.content.natural_key()))
        if ca.artifact:
            a_key = str(ca.artifact.sha256)
        return c_key, a_key


class RemoteArtifactQuerySet(models.QuerySet):
    """QuerySet that provides methods for querying RemoteArtifact."""

    def acs(self):
        """Return RemoteArtifacts if they belong to an ACS in the same Domain."""
        domain_pk = get_domain_pk()
        return self.filter(remote__alternatecontentsource__isnull=False, pulp_domain=domain_pk)

    def order_by_acs(self):
        """Order RemoteArtifacts returning ones with ACSes first."""
        return self.annotate(acs_count=models.Count("remote__alternatecontentsource")).order_by(
            "-acs_count"
        )


class RemoteArtifact(BaseModel, QueryMixin):
    """
    Represents a content artifact that is provided by a remote (external) repository.

    Remotes that want to support deferred download policies should use this model to store
    information required for downloading an Artifact at some point in the future. At a minimum this
    includes the URL, the ContentArtifact, and the Remote that created it. It can also store
    expected size and any expected checksums.

    Fields:

        url (models.TextField): The URL where the artifact can be retrieved.
        size (models.BigIntegerField): The expected size of the file in bytes.
        md5 (models.CharField): The expected MD5 checksum of the file.
        sha1 (models.CharField): The expected SHA-1 checksum of the file.
        sha224 (models.CharField): The expected SHA-224 checksum of the file.
        sha256 (models.CharField): The expected SHA-256 checksum of the file.
        sha384 (models.CharField): The expected SHA-384 checksum of the file.
        sha512 (models.CharField): The expected SHA-512 checksum of the file.

    Relations:

        content_artifact (pulpcore.app.models.ForeignKey)
            ContentArtifact associated with this RemoteArtifact.
        remote (django.db.models.ForeignKey) Remote that created the
            RemoteArtifact.
        pulp_domain (django.db.models.ForeignKey) Domain the RemoteArtifact is a part of.
    """

    url = models.TextField(validators=[validators.URLValidator])
    size = models.BigIntegerField(null=True)
    md5 = models.CharField(max_length=32, null=True, db_index=True)
    sha1 = models.CharField(max_length=40, null=True, db_index=True)
    sha224 = models.CharField(max_length=56, null=True, db_index=True)
    sha256 = models.CharField(max_length=64, null=True, db_index=True)
    sha384 = models.CharField(max_length=96, null=True, db_index=True)
    sha512 = models.CharField(max_length=128, null=True, db_index=True)

    content_artifact = models.ForeignKey(ContentArtifact, on_delete=models.CASCADE)
    remote = models.ForeignKey("Remote", on_delete=models.CASCADE)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    objects = BulkCreateManager.from_queryset(RemoteArtifactQuerySet)()

    def validate_checksums(self):
        """Validate if RemoteArtifact has allowed checksum or no checksum at all."""
        if not any(
            [
                checksum_type
                for checksum_type in ALL_KNOWN_CONTENT_CHECKSUMS
                if getattr(self, checksum_type, False)
            ]
        ):
            return
        if not any(
            [
                checksum_type
                for checksum_type in Artifact.DIGEST_FIELDS
                if getattr(self, checksum_type, False)
            ]
        ):
            raise UnsupportedDigestValidationError(
                _(
                    "On-demand content located at the url {} contains forbidden checksum type,"
                    "thus cannot be synced."
                    "You can allow checksum type with 'ALLOWED_CONTENT_CHECKSUMS' setting."
                ).format(self.url)
            )

    class Meta:
        unique_together = ("content_artifact", "remote", "pulp_domain")


class SigningService(BaseModel):
    """
    A model used for producing signatures.

    Fields:
        name (models.TextField):
            A unique name describing a script (or executable) used for signing.
        public_key (models.TextField):
            The value of the public key.
        script (models.TextField):
            An absolute path to an external signing script (or executable).

    """

    name = models.TextField(db_index=True, unique=True)
    public_key = models.TextField()
    pubkey_fingerprint = models.TextField()
    script = models.TextField()

    def _env_variables(self, env_vars=None):
        guid = get_guid()
        env = {
            "PULP_SIGNING_KEY_FINGERPRINT": self.pubkey_fingerprint,
            "CORRELATION_ID": guid if guid else "",
        }
        if env_vars:
            env.update(env_vars)
        return env

    def sign(self, filename, env_vars=None):
        """
        Signs the file provided via 'filename' by invoking an external script (or executable).

        The external script is run as a subprocess. This is done in the expectation that the script
        has been validated as an external signing service by the validate() method. This validation
        is currently only done when creating the signing service object, but not at the time of use.

        Args:
            filename (str): A relative path to a file which is intended to be signed.
            env_vars (dict): dictionary of environment variables

        Raises:
            RuntimeError: If the return code of the script is not equal to 0.

        Returns:
            A dictionary as validated by the validate() method.
        """
        completed_process = subprocess.run(
            [self.script, filename],
            env=self._env_variables(env_vars),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if completed_process.returncode != 0:
            raise RuntimeError(str(completed_process.stderr))

        try:
            return_value = json.loads(completed_process.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("The signing service script did not return valid JSON!")

        return return_value

    async def asign(self, filename, env_vars=None):
        """Async version of sign."""
        process = await asyncio.create_subprocess_exec(
            self.script,
            filename,
            env=self._env_variables(env_vars),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(str(stderr))

        try:
            return_value = json.loads(stdout)
        except json.JSONDecodeError:
            raise RuntimeError("The signing service script did not return valid JSON!")

        return return_value

    def validate(self):
        """
        Ensure that the external signing script produces the desired behaviour.

        With desired behaviour we mean the behaviour as validated by this method. Subclasses are
        required to implement this method. Works by calling the sign() method on some test data, and
        verifying that any desired signatures/signature files are returned and are valid. Must also
        enforce the desired return value format of the sign() method.

        Raises:
            RuntimeError: If the script failed to produce the desired outcome for the test data.
        """
        raise NotImplementedError("Subclasses must implement a validate() method.")

    def save(self, *args, **kwargs):
        """
        Save a signing service to the database (unless it fails to validate).
        """
        if not self.public_key:
            raise RuntimeError(
                _(
                    "The public key needs to be specified during the new instance creation. Other "
                    "ways of providing the public key are considered deprecated as of the release "
                    "(3.10)."
                )
            )

        self.validate()
        super().save(*args, **kwargs)

    @hook(BEFORE_UPDATE)
    def on_update(self):
        raise RuntimeError(
            _(
                "The signing service is immutable. It is advised to create a new signing service "
                "when a change is required."
            )
        )


class AsciiArmoredDetachedSigningService(SigningService):
    """
    A model used for creating detached ASCII armored signatures.
    """

    def validate(self):
        """
        Validate a signing service for a detached ASCII armored signature.

        The validation seeks to ensure that the sign() method returns a dict as follows:

        {"file": "signed_file.xml", "signature": "signed_file.asc"}

        The method creates a file with some content, signs the file, and checks if the
        signature can be verified by the provided public key.

        Raises:
            RuntimeError: If the validation has failed.
        """
        with tempfile.TemporaryDirectory(dir=settings.WORKING_DIRECTORY) as temp_directory_name:
            with tempfile.NamedTemporaryFile(dir=temp_directory_name) as temp_file:
                temp_file.write(b"arbitrary data")
                temp_file.flush()
                return_value = self.sign(temp_file.name)

                gpg_verify(self.public_key, return_value["signature"], temp_file.name)
