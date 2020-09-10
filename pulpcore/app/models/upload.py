import hashlib

from django.core.files.base import ContentFile
from django.db import models
from rest_framework import serializers

from pulpcore.app.models import BaseModel, fields, storage
from pulpcore.app.models.content import HandleTempFilesMixin


class Upload(BaseModel):
    """
    A chunked upload. Stores chunks until used to create an artifact, etc.

    Fields:

        size (models.BigIntegerField): The size of the file in bytes.
    """

    size = models.BigIntegerField()

    def append(self, chunk, offset, sha256=None):
        """
        Append a chunk to an upload.

        Args:
            chunk (File): Binary file to append to the upload file.
            offset (int): First byte position to write chunk to.
        """
        chunk_read = chunk.read()
        current_sha256 = hashlib.sha256(chunk_read).hexdigest()
        if sha256 and sha256 != current_sha256:
            raise serializers.ValidationError("Checksum does not match chunk upload.")

        upload_chunk = UploadChunk(upload=self, offset=offset, size=len(chunk))
        upload_chunk.file.save("", ContentFile(chunk_read))


class UploadChunk(HandleTempFilesMixin, BaseModel):
    """
    A chunk for an uploaded file.

    Fields:

        file (fields.ArtifactFileField): A file where the uploaded chunk is stored.
        upload (models.ForeignKey): Upload this chunk belongs to.
        offset (models.BigIntegerField): Start of the chunk in bytes.
        size (models.BigIntegerField): Size of the chunk in bytes.
    """

    def storage_path(self, name):
        """
        Callable used by FileField to determine where the uploaded file should be stored.

        Args:
            name (str): Original name of uploaded file. It is ignored by this method because the
                pulp_id is used to determine a file path instead.
        """
        return storage.get_upload_chunk_file_path(self.pulp_id)

    file = fields.FileField(null=False, upload_to=storage_path, max_length=255)
    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="chunks")
    offset = models.BigIntegerField()
    size = models.BigIntegerField()

    def delete(self, *args, **kwargs):
        """
        Delete UploadChunk model and the file associated with the model

        Args:
            args (list): list of positional arguments for Model.delete()
            kwargs (dict): dictionary of keyword arguments to pass to Model.delete()
        """
        super().delete(*args, **kwargs)
        self.file.delete(save=False)
