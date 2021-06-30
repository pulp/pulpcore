import hashlib
import os

from django.core.files.base import ContentFile
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from rest_framework import serializers

from pulpcore.app.models import BaseModel, fields, storage


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
        filename = os.path.basename(upload_chunk.storage_path(""))
        upload_chunk.file.save(filename, ContentFile(chunk_read))


class UploadChunk(BaseModel):
    """
    A chunk for an uploaded file.

    Fields:

        file (fields.FileField): A file where the uploaded chunk is stored.
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


@receiver(post_delete, sender=UploadChunk)
def upload_chunk_delete(instance, **kwargs):
    instance.file.delete(save=False)
