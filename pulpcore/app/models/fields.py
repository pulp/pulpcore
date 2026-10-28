import json
import logging
import os
from functools import lru_cache
from gettext import gettext as _

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import FileField, JSONField, Lookup
from django.db.models.fields import Field, TextField
from django.utils.encoding import force_bytes, force_str

from pulpcore.app.files import TemporaryDownloadedFile

_logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _fernet():
    # Cache the enryption keys once per application.
    _logger.debug(f"Loading encryption key from {settings.DB_ENCRYPTION_KEY}")
    with open(settings.DB_ENCRYPTION_KEY, "rb") as key_file:
        return MultiFernet(
            [
                Fernet(key.strip())
                for key in key_file.readlines()
                if not key.startswith(b"#") and key.strip() != b""
            ]
        )


class ArtifactFileField(FileField):
    """
    A custom FileField that always saves files to location specified by 'upload_to'.

    The field can be set as either a path to the file or File object. In both cases the file is
    moved or copied to the location specified by 'upload_to' field parameter.
    """

    def pre_save(self, model_instance, add):
        """
        Return FieldFile object which specifies path to the file to be stored in database.

        There are two ways to get artifact into Pulp: sync and upload.

        The upload case:
         - assigning a File object sets _committed=False, meaning this FieldFile has not saved it
         - the File object may still refer to a file already in artifact storage, so check any
           absolute source path before saving
         - Django pre_save writes the File object to upload_to without extra handling here

        The sync case:
         - assigning a path sets _committed=True, even when the file is in a temporary location
         - a file already at upload_to stays in place; other files in artifact storage are rejected
         - TemporaryDownloadedFile wraps an outside source so storage can move or copy it
         - when needed, mark the file uncommitted so Django pre_save stores it at upload_to

        Args:
            model_instance (`class::pulpcore.plugin.Artifact`): The instance this field belongs to.
            add (bool): Whether the instance is being saved to the database for the first time.
                        Ignored by Django pre_save method.

        Returns:
            FieldFile object just before saving.

        """
        file = model_instance.file
        # A path assignment creates a committed FieldFile whose name is the source path.
        # A File assignment is uncommitted, so inspect the wrapped File's source name.
        source_path = file.name if file._committed else file.file.name
        if not file._committed and (not source_path or not os.path.isabs(source_path)):
            # A relative File name does not identify a location in artifact storage.
            return super().pre_save(model_instance, add)

        artifact_storage_path = self.upload_to(model_instance, "")

        stored_file_path = None
        stored_artifact_dir = None
        try:
            stored_file_path = file.storage.path(artifact_storage_path)
            stored_artifact_dir = file.storage.path("artifact")
        except NotImplementedError:
            # Object storage backends do not have absolute filesystem paths.
            pass

        already_in_place = source_path in (artifact_storage_path, stored_file_path)
        # Match the artifact directory, not other names beginning with "artifact".
        artifact_storage_prefixes = [os.path.join("artifact", "")]
        if stored_artifact_dir is not None:
            artifact_storage_prefixes.append(os.path.join(stored_artifact_dir, ""))
        is_in_artifact_storage = source_path.startswith(tuple(artifact_storage_prefixes))

        if not already_in_place and is_in_artifact_storage:
            raise ValueError(
                _(
                    "The file referenced by the Artifact is already present in "
                    "Artifact storage. Files must be stored outside this location "
                    "prior to Artifact creation."
                )
            )
        if not file._committed:
            return super().pre_save(model_instance, add)

        if file.name != artifact_storage_path:
            if not already_in_place:
                file._file = TemporaryDownloadedFile(open(file.name, "rb"))
            # Let Django save the source and record its storage-relative name.
            file._committed = False

        return super().pre_save(model_instance, add)


class EncryptedTextField(TextField):
    """A field that encrypts text using settings.DB_ENCRYPTION_KEY."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("primary_key"):
            raise ImproperlyConfigured("EncryptedTextField does not support primary_key=True.")
        if kwargs.get("unique"):
            raise ImproperlyConfigured("EncryptedTextField does not support unique=True.")
        if kwargs.get("db_index"):
            raise ImproperlyConfigured("EncryptedTextField does not support db_index=True.")
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        if value is not None:
            assert isinstance(value, str)
            value = force_str(_fernet().encrypt(force_bytes(value)))
        return super().get_prep_value(value)

    def from_db_value(self, value, expression, connection):
        if value is not None:
            value = force_str(_fernet().decrypt(force_bytes(value)))
        return value


class EncryptedJSONField(JSONField):
    """A Field that encrypts the JSON text using settings.DP_ENCRYPTION_KEY."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("primary_key"):
            raise ImproperlyConfigured("EncryptedJSONField does not support primary_key=True.")
        if kwargs.get("unique"):
            raise ImproperlyConfigured("EncryptedJSONField does not support unique=True.")
        if kwargs.get("db_index"):
            raise ImproperlyConfigured("EncryptedJSONField does not support db_index=True.")
        super().__init__(*args, **kwargs)

    def encrypt(self, value):
        if isinstance(value, dict):
            return {k: self.encrypt(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple, set)):
            return [self.encrypt(v) for v in value]

        return force_str(_fernet().encrypt(force_bytes(json.dumps(value, cls=self.encoder))))

    def decrypt(self, value):
        if isinstance(value, dict):
            return {k: self.decrypt(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple, set)):
            return [self.decrypt(v) for v in value]

        dec_value = force_str(_fernet().decrypt(force_bytes(value)))
        return json.loads(dec_value, cls=self.decoder)

    def get_prep_value(self, value):
        if value is not None:
            if hasattr(value, "as_sql"):
                return value
            value = self.encrypt(value)
        return super().get_prep_value(value)

    def from_db_value(self, value, expression, connection):
        if value is not None:
            value = self.decrypt(super().from_db_value(value, expression, connection))
        return value


class RelativePathField(TextField):
    def db_type(self, connection):
        return "relative_path"


@Field.register_lookup
class NotEqualLookup(Lookup):
    # this is copied from https://docs.djangoproject.com/en/3.2/howto/custom-lookups/
    lookup_name = "ne"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "%s <> %s" % (lhs, rhs), params
