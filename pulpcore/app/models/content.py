"""
Content related Django models.
"""
from gettext import gettext as _

import json
import tempfile
import shutil
import subprocess

import gnupg

from itertools import chain

from django.conf import settings
from django.core import validators
from django.core.files.storage import default_storage
from django.db import IntegrityError, models, transaction
from django.forms.models import model_to_dict
from django_lifecycle import BEFORE_UPDATE, BEFORE_SAVE, hook

from pulpcore.constants import ALL_KNOWN_CONTENT_CHECKSUMS
from pulpcore.app import pulp_hashlib
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
        self.file.delete(save=False)


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
        timestamp_of_interest (models.DateTimeField): timestamp that prevents orphan cleanup
    """

    def storage_path(self, name):
        """
        Callable used by FileField to determine where the uploaded file should be stored.

        Args:
            name (str): Original name of uploaded file. It is ignored by this method because the
                sha256 checksum is used to determine a file path instead.
        """
        return storage.get_artifact_path(self.sha256)

    file = fields.ArtifactFileField(null=False, upload_to=storage_path, max_length=255)
    size = models.BigIntegerField(null=False)
    md5 = models.CharField(max_length=32, null=True, unique=False, db_index=True)
    sha1 = models.CharField(max_length=40, null=True, unique=False, db_index=True)
    sha224 = models.CharField(max_length=56, null=True, unique=False, db_index=True)
    sha256 = models.CharField(max_length=64, null=False, unique=True, db_index=True)
    sha384 = models.CharField(max_length=96, null=True, unique=True, db_index=True)
    sha512 = models.CharField(max_length=128, null=True, unique=True, db_index=True)
    timestamp_of_interest = models.DateTimeField(auto_now=True)

    objects = BulkCreateManager()

    # All available digest fields ordered by algorithm strength.
    DIGEST_FIELDS = _DIGEST_FIELDS

    # All available digest fields ordered by relative frequency
    # (Better average-case performance in some algorithms with fallback)
    COMMON_DIGEST_FIELDS = _COMMON_DIGEST_FIELDS

    # Available, reliable digest fields ordered by algorithm strength.
    RELIABLE_DIGEST_FIELDS = _RELIABLE_DIGEST_FIELDS

    # Digest-fields that are NOT ALLOWED
    FORBIDDEN_DIGESTS = _FORBIDDEN_DIGESTS

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
                return models.Q(**{digest_name: digest_value})
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
        :class:`~pulpcore.app.files.PulpTemporaryUploadedFile`.

        Args:
            file (:class:`~pulpcore.app.files.PulpTemporaryUploadedFile` or str): The
                PulpTemporaryUploadedFile to create the Artifact from or a string with the full path
                to the file on disk.
            expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
                value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
            expected_size (int): The number of bytes the download is expected to have.

        Raises:
            :class:`~pulpcore.exceptions.DigestValidationError`: When any of the ``expected_digest``
                values don't match the digest of the data
            :class:`~pulpcore.exceptions.SizeValidationError`: When the ``expected_size`` value
                doesn't match the size of the data
            :class:`~pulpcore.exceptions.UnsupportedDigestValidationError`: When any of the
                ``expected_digest`` algorithms aren't in the ALLOWED_CONTENT_CHECKSUMS list
        Returns:
            An in-memory, unsaved :class:`~pulpcore.plugin.models.Artifact`
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
                raise SizeValidationError()

        if expected_digests:
            for algorithm, expected_digest in expected_digests.items():
                if algorithm not in hashers:
                    raise UnsupportedDigestValidationError(
                        _("Checksum algorithm {} forbidden for this Pulp instance.").format(
                            algorithm
                        )
                    )
                if expected_digest != hashers[algorithm].hexdigest():
                    raise DigestValidationError()

        attributes = {"size": size, "file": file}
        for algorithm in Artifact.DIGEST_FIELDS:
            attributes[algorithm] = hashers[algorithm].hexdigest()

        return Artifact(**attributes)

    @classmethod
    def from_pulp_temporary_file(cls, temp_file):
        """
        Creates an Artifact from PulpTemporaryFile.

        Returns:
            An saved :class:`~pulpcore.plugin.models.Artifact`
        """
        artifact_file = default_storage.open(temp_file.file.name)
        with tempfile.NamedTemporaryFile("wb") as new_file:
            shutil.copyfileobj(artifact_file, new_file)
            new_file.flush()
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
    """

    def storage_path(self, name):
        """
        Callable used by FileField to determine where the uploaded file should be stored.

        Args:
            name (str): Original name of uploaded file. It is ignored by this method because the
                pulp_id is used to determine a file path instead.
        """
        return storage.get_temp_file_path(self.pulp_id)

    file = fields.ArtifactFileField(null=False, upload_to=storage_path, max_length=255)

    @staticmethod
    def init_and_validate(file, expected_digests=None, expected_size=None):
        """
        Initialize an in-memory PulpTemporaryFile from a file, and validate digest and size info.

        This accepts both a path to a file on-disk or a
        :class:`~pulpcore.app.files.PulpTemporaryUploadedFile`.

        Args:
            file (:class:`~pulpcore.app.files.PulpTemporaryUploadedFile` or str): The
                PulpTemporaryUploadedFile to create the PulpTemporaryFile from or a string with the
                full path to the file on disk.
            expected_digests (dict): Keyed on the algorithm name provided by hashlib and stores the
                value of the expected digest. e.g. {'md5': '912ec803b2ce49e4a541068d495ab570'}
            expected_size (int): The number of bytes the download is expected to have.

        Raises:
            :class:`~pulpcore.exceptions.DigestValidationError`: When any of the ``expected_digest``
                values don't match the digest of the data
            :class:`~pulpcore.exceptions.SizeValidationError`: When the ``expected_size`` value
                doesn't match the size of the data
            :class:`~pulpcore.exceptions.UnsupportedDigestValidationError`: When any of the
                ``expected_digest`` algorithms aren't in the ALLOWED_CONTENT_CHECKSUMS list

        Returns:
            An in-memory, unsaved :class:`~pulpcore.plugin.models.PulpTemporaryFile`
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
                raise SizeValidationError()

        if expected_digests:
            for algorithm, expected_digest in expected_digests.items():
                if algorithm not in hashers:
                    raise UnsupportedDigestValidationError(
                        _("Checksum algorithm {} forbidden for this Pulp instance.").format(
                            algorithm
                        )
                    )
                if expected_digest != hashers[algorithm].hexdigest():
                    raise DigestValidationError()

        return PulpTemporaryFile(file=file)


class Content(MasterModel, QueryMixin):
    """
    A piece of managed content.

    Fields:
        upstream_id (models.UUIDField) : identifier of content imported from an 'upstream' Pulp
        timestamp_of_interest (models.DateTimeField): timestamp that prevents orphan cleanup

    Relations:

        _artifacts (models.ManyToManyField): Artifacts related to Content through ContentArtifact
    """

    TYPE = "content"
    repo_key_fields = ()  # Used by pulpcore.plugin.repo_version_utils.remove_duplicates
    upstream_id = models.UUIDField(null=True)  # Used by PulpImport/Export processing

    _artifacts = models.ManyToManyField(Artifact, through="ContentArtifact")
    timestamp_of_interest = models.DateTimeField(auto_now=True)

    objects = BulkCreateManager()

    class Meta:
        verbose_name_plural = "content"
        unique_together = ()

    @classmethod
    def natural_key_fields(cls):
        """
        Returns a tuple of the natural key fields which usually equates to unique_together fields
        """
        return tuple(chain.from_iterable(cls._meta.unique_together))

    def natural_key(self):
        """
        Get the model's natural key based on natural_key_fields.

        Returns:
            tuple: The natural key.
        """
        return tuple(getattr(self, f) for f in self.natural_key_fields())

    def natural_key_dict(self):
        """
        Get the model's natural key as a dictionary of keys and values.
        """
        to_return = {}
        for key in self.natural_key_fields():
            to_return[key] = getattr(self, key)
        return to_return

    @staticmethod
    def init_from_artifact_and_relative_path(artifact, relative_path):
        """
        Return an instance of the specific content by inspecting an artifact.

        Plugin writers are expected to override this method with an implementation for a specific
        content type.

        For example::

            if path.isabs(relative_path):
                raise ValueError(_("Relative path can't start with '/'."))
            return FileContent(relative_path=relative_path, digest=artifact.sha256)

        Args:
            artifact (:class:`~pulpcore.plugin.models.Artifact`): An instance of an Artifact
            relative_path (str): Relative path for the content

        Raises:
            ValueError: If relative_path starts with a '/'.

        Returns:
            An un-saved instance of :class:`~pulpcore.plugin.models.Content` sub-class.
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

        content_artifact (:class:`pulpcore.app.models.ForeignKey`):
            ContentArtifact associated with this RemoteArtifact.
        remote (:class:`django.db.models.ForeignKey`): Remote that created the
            RemoteArtifact.
    """

    url = models.TextField(validators=[validators.URLValidator])
    size = models.BigIntegerField(null=True)
    md5 = models.CharField(max_length=32, null=True)
    sha1 = models.CharField(max_length=40, null=True)
    sha224 = models.CharField(max_length=56, null=True)
    sha256 = models.CharField(max_length=64, null=True)
    sha384 = models.CharField(max_length=96, null=True)
    sha512 = models.CharField(max_length=128, null=True)

    content_artifact = models.ForeignKey(ContentArtifact, on_delete=models.CASCADE)
    remote = models.ForeignKey("Remote", on_delete=models.CASCADE)

    objects = BulkCreateManager()

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
        unique_together = ("content_artifact", "remote")


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

    def sign(self, filename):
        """
        Signs the file provided via 'filename' by invoking an external script (or executable).

        The external script is run as a subprocess. This is done in the expectation that the script
        has been validated as an external signing service by the validate() method. This validation
        is currently only done when creating the signing service object, but not at the time of use.

        Args:
            filename (str): A relative path to a file which is intended to be signed.

        Raises:
            RuntimeError: If the return code of the script is not equal to 0.

        Returns:
            A dictionary as validated by the validate() method.
        """
        completed_process = subprocess.run(
            [self.script, filename], env={}, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        if completed_process.returncode != 0:
            raise RuntimeError(str(completed_process.stderr))

        try:
            return_value = json.loads(completed_process.stdout)
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
        gpg = gnupg.GPG()
        with tempfile.TemporaryDirectory() as temp_directory_name:
            with tempfile.NamedTemporaryFile(dir=temp_directory_name) as temp_file:
                temp_file.write(b"arbitrary data")
                temp_file.flush()
                signed = self.sign(temp_file.name)

                with open(signed["signature"], "rb") as fp:
                    verified = gpg.verify_file(fp, temp_file.name)
                    if verified.trust_level is None or verified.trust_level < verified.TRUST_FULLY:
                        raise RuntimeError(
                            _(
                                "The signature could not be verified or the trust level is too "
                                "low. The signing script may generate invalid signatures."
                            )
                        )
                    elif verified.pubkey_fingerprint != self.pubkey_fingerprint:
                        raise RuntimeError(
                            _(
                                "Fingerprints of the provided public key and the verified public "
                                "key are not equal. The signing script is probably not valid."
                            )
                        )
