"""
Content related Django models.
"""
import json
import hashlib
import tempfile
import subprocess

import gnupg

from itertools import chain

from django.core import validators
from django.db import IntegrityError, models, transaction
from django.forms.models import model_to_dict

from pulpcore.app.models import MasterModel, BaseModel, fields, storage
from pulpcore.exceptions import DigestValidationError, SizeValidationError


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


class Artifact(BaseModel):
    """
    A file associated with a piece of content.

    When calling `save()` on an Artifact, if the file is not stored in Django's storage backend, it
    is moved into place then.

    Artifact is compatible with Django's `bulk_create()` method.


    Fields:

        file (models.FileField): The stored file. This field should be set using an absolute path to
            a temporary file. It also accepts `class:django.core.files.File`.
        size (models.IntegerField): The size of the file in bytes.
        md5 (models.CharField): The MD5 checksum of the file.
        sha1 (models.CharField): The SHA-1 checksum of the file.
        sha224 (models.CharField): The SHA-224 checksum of the file.
        sha256 (models.CharField): The SHA-256 checksum of the file.
        sha384 (models.CharField): The SHA-384 checksum of the file.
        sha512 (models.CharField): The SHA-512 checksum of the file.
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
    md5 = models.CharField(max_length=32, null=False, unique=False, db_index=True)
    sha1 = models.CharField(max_length=40, null=False, unique=False, db_index=True)
    sha224 = models.CharField(max_length=56, null=False, unique=False, db_index=True)
    sha256 = models.CharField(max_length=64, null=False, unique=True, db_index=True)
    sha384 = models.CharField(max_length=96, null=False, unique=True, db_index=True)
    sha512 = models.CharField(max_length=128, null=False, unique=True, db_index=True)

    objects = BulkCreateManager()

    # All digest fields ordered by algorithm strength.
    DIGEST_FIELDS = (
        'sha512',
        'sha384',
        'sha256',
        'sha224',
        'sha1',
        'md5',
    )

    # Reliable digest fields ordered by algorithm strength.
    RELIABLE_DIGEST_FIELDS = DIGEST_FIELDS[:-3]

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
        for field in Artifact.RELIABLE_DIGEST_FIELDS:
            digest = getattr(self, field)
            if not digest:
                continue
            if digest == getattr(other, field):
                return True
        return False

    def save(self, *args, **kwargs):
        """
        Saves Artifact model and closes the file associated with the Artifact

        Args:
            args (list): list of positional arguments for Model.save()
            kwargs (dict): dictionary of keyword arguments to pass to Model.save()
        """
        try:
            super().save(*args, **kwargs)
            self.file.close()
        except Exception:
            self.file.close()
            raise

    def delete(self, *args, **kwargs):
        """
        Deletes Artifact model and the file associated with the Artifact

        Args:
            args (list): list of positional arguments for Model.delete()
            kwargs (dict): dictionary of keyword arguments to pass to Model.delete()
        """
        super().delete(*args, **kwargs)
        self.file.delete(save=False)

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

        Returns:
            An in-memory, unsaved :class:`~pulpcore.plugin.models.Artifact`
        """
        if isinstance(file, str):
            with open(file, 'rb') as f:
                hashers = {n: hashlib.new(n) for n in Artifact.DIGEST_FIELDS}
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
                if expected_digest != hashers[algorithm].hexdigest():
                    raise DigestValidationError()

        attributes = {'size': size, 'file': file}
        for algorithm in Artifact.DIGEST_FIELDS:
            attributes[algorithm] = hashers[algorithm].hexdigest()

        return Artifact(**attributes)


class Content(MasterModel, QueryMixin):
    """
    A piece of managed content.

    Relations:

        _artifacts (models.ManyToManyField): Artifacts related to Content through ContentArtifact
    """
    TYPE = 'content'
    repo_key_fields = ()  # Used by pulpcore.plugin.repo_version_utils.remove_duplicates

    _artifacts = models.ManyToManyField(Artifact, through='ContentArtifact')

    objects = BulkCreateManager()

    class Meta:
        verbose_name_plural = 'content'
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


class ContentArtifact(BaseModel, QueryMixin):
    """
    A relationship between a Content and an Artifact.

    Serves as a through model for the '_artifacts' ManyToManyField in Content.
    Artifact is protected from deletion if it's present in a ContentArtifact relationship.
    """
    artifact = models.ForeignKey(Artifact, on_delete=models.PROTECT, null=True)
    content = models.ForeignKey(Content, on_delete=models.CASCADE)
    relative_path = models.TextField()

    objects = BulkCreateManager()

    class Meta:
        unique_together = ('content', 'relative_path')


class RemoteArtifact(BaseModel, QueryMixin):
    """
    Represents a content artifact that is provided by a remote (external) repository.

    Remotes that want to support deferred download policies should use this model to store
    information required for downloading an Artifact at some point in the future. At a minimum this
    includes the URL, the ContentArtifact, and the Remote that created it. It can also store
    expected size and any expected checksums.

    Fields:

        url (models.TextField): The URL where the artifact can be retrieved.
        size (models.IntegerField): The expected size of the file in bytes.
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
    size = models.IntegerField(null=True)
    md5 = models.CharField(max_length=32, null=True)
    sha1 = models.CharField(max_length=40, null=True)
    sha224 = models.CharField(max_length=56, null=True)
    sha256 = models.CharField(max_length=64, null=True)
    sha384 = models.CharField(max_length=96, null=True)
    sha512 = models.CharField(max_length=128, null=True)

    content_artifact = models.ForeignKey(ContentArtifact, on_delete=models.CASCADE)
    remote = models.ForeignKey('Remote', on_delete=models.CASCADE)

    objects = BulkCreateManager()

    class Meta:
        unique_together = ('content_artifact', 'remote')


class SigningService(BaseModel):
    """
    A model used for producing signatures.

    Fields:
        name (models.TextField): A unique name describing a script used for signing.
        script (models.TextField): An absolute path to the script.

    """
    name = models.TextField(db_index=True, unique=True)
    script = models.TextField()

    def sign(self, filename):
        """
        Sign a passed file.

        Subclasses are required to implement this method. The method shall invoke an external
        signing script that creates a signature for the passed filename.

        Args:
            filename (str): A relative path to a file which is intended to be signed.

        """
        raise NotImplementedError('Subclasses must implement their own method for signing.')


class AsciiArmoredDetachedSigningService(SigningService):
    """
    A model used for creating detached ascii armored signatures.
    """

    def save(self, *args, **kwargs):
        """
        Validate and save a signing service for an ASCII armored signature.

        Before saving the signing service to the database, it is required to check if the service's
        output corresponds to a proposed output format and creates valid signatures.

        In this case, Pulp creates a file with random content, signs the file, and checks if the
        signature can be verified by a provided public key. If the signature was verified without
        errors, the signing service object is saved to the database.
        """
        gpg = gnupg.GPG()
        with tempfile.TemporaryDirectory() as temp_directory_name:
            with tempfile.NamedTemporaryFile(dir=temp_directory_name) as temp_file:
                temp_file.write(b"random-data")
                try:
                    data = self.sign(temp_file.name)
                except RuntimeError:
                    raise

                with open(data["signature"], "rb") as fp:
                    with open(data["key"], "rb") as key:
                        import_result = gpg.import_keys(key.read())
                        verified = gpg.verify_file(fp, temp_file.name)
                        if verified.trust_level is None \
                                or verified.trust_level < verified.TRUST_FULLY:
                            raise RuntimeError(
                                "A signature could not be verified or a trust level is too low. "
                                "The signing script may generate invalid signatures."
                            )
                        elif verified.pubkey_fingerprint != import_result.fingerprints[0]:
                            raise RuntimeError(
                                "Fingerprints of a provided public key and a verified public key "
                                "are not equal. The signing script is probably not valid.")
                        else:
                            super().save(*args, **kwargs)

    def sign(self, filename):
        """
        Create an ASCII armored signature for the passed filename.

        Args:
            filename (str): A relative path to a file which is intended to be signed.

        Raises:
            RuntimeError: If a return code of the script is not equal to 0, indicating a failure.

        Returns:
            A dictionary in the following format::

                {"file": "signed_file.xml", "signature": "signed_file.asc", "key": "public.key"}

        """
        completed_process = subprocess.run(
            [self.script, filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if completed_process.returncode != 0:
            raise RuntimeError(str(completed_process.stderr))

        return json.loads(completed_process.stdout)
