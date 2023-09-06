import json
import logging
import os
from gettext import gettext as _

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Lookup, FileField, JSONField
from django.db.models.fields import Field, TextField
from django.utils.encoding import force_bytes, force_str
from django.utils.functional import cached_property


from pulpcore.app.files import TemporaryDownloadedFile

_logger = logging.getLogger(__name__)


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

        The upload case
         - file is not stored yet, aka file._committed = False
         - nothing to do here in addition to Django pre_save actions

        The sync case:
         - file is already stored in a temporary location, aka file._committed = True
         - it needs to be moved into Pulp artifact storage if it's not there
         - TemporaryDownloadedFile takes care of correctly set storage path
         - only then Django pre_save actions should be performed

        Args:
            model_instance (`class::pulpcore.plugin.Artifact`): The instance this field belongs to.
            add (bool): Whether the instance is being saved to the database for the first time.
                        Ignored by Django pre_save method.

        Returns:
            FieldFile object just before saving.

        """
        file = model_instance.file
        artifact_storage_path = self.upload_to(model_instance, "")

        already_in_place = file.name in [
            artifact_storage_path,
            os.path.join(settings.MEDIA_ROOT, artifact_storage_path),
        ]
        is_in_artifact_storage = file.name.startswith(os.path.join(settings.MEDIA_ROOT, "artifact"))

        if not already_in_place and is_in_artifact_storage:
            raise ValueError(
                _(
                    "The file referenced by the Artifact is already present in "
                    "Artifact storage. Files must be stored outside this location "
                    "prior to Artifact creation."
                )
            )

        move = file._committed and file.name != artifact_storage_path
        if move:
            if not already_in_place:
                file._file = TemporaryDownloadedFile(open(file.name, "rb"))
            file._committed = False

        return super().pre_save(model_instance, add)


class EncryptedTextField(TextField):
    """A field mixin that encrypts text using settings.DB_ENCRYPTION_KEY."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("primary_key"):
            raise ImproperlyConfigured("EncryptedTextField does not support primary_key=True.")
        if kwargs.get("unique"):
            raise ImproperlyConfigured("EncryptedTextField does not support unique=True.")
        if kwargs.get("db_index"):
            raise ImproperlyConfigured("EncryptedTextField does not support db_index=True.")
        super().__init__(*args, **kwargs)

    @cached_property
    def _fernet(self):
        _logger.debug(f"Loading encryption key from {settings.DB_ENCRYPTION_KEY}")
        with open(settings.DB_ENCRYPTION_KEY, "rb") as key_file:
            return Fernet(key_file.read())

    def get_prep_value(self, value):
        if value is not None:
            assert isinstance(value, str)
            value = force_str(self._fernet.encrypt(force_bytes(value)))
        return super().get_prep_value(value)

    def from_db_value(self, value, expression, connection):
        if value is not None:
            value = force_str(self._fernet.decrypt(force_bytes(value)))
        return value


class EncryptedJSONField(JSONField):
    """A Field mixin that encrypts the JSON text using settings.DP_ENCRYPTION_KEY."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("primary_key"):
            raise ImproperlyConfigured("EncryptedJSONField does not support primary_key=True.")
        if kwargs.get("unique"):
            raise ImproperlyConfigured("EncryptedJSONField does not support unique=True.")
        if kwargs.get("db_index"):
            raise ImproperlyConfigured("EncryptedJSONField does not support db_index=True.")
        super().__init__(*args, **kwargs)

    @cached_property
    def _fernet(self):
        _logger.debug(f"Loading encryption key from {settings.DB_ENCRYPTION_KEY}")
        with open(settings.DB_ENCRYPTION_KEY, "rb") as key_file:
            return Fernet(key_file.read())

    def encrypt(self, value):
        if isinstance(value, dict):
            return {k: self.encrypt(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple, set)):
            return [self.encrypt(v) for v in value]

        return force_str(self._fernet.encrypt(force_bytes(repr(value))))

    def decrypt(self, value):
        if isinstance(value, dict):
            return {k: self.decrypt(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple, set)):
            return [self.decrypt(v) for v in value]

        dec_value = force_str(self._fernet.decrypt(force_bytes(value)))
        try:
            return json.loads(dec_value, cls=self.decoder)
        except json.JSONDecodeError:
            return eval(dec_value)

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


@Field.register_lookup
class NotEqualLookup(Lookup):
    # this is copied from https://docs.djangoproject.com/en/3.2/howto/custom-lookups/
    lookup_name = "ne"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = lhs_params + rhs_params
        return "%s <> %s" % (lhs, rhs), params
