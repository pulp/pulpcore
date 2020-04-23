import hashlib

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import models
from rest_framework import serializers

from pulpcore.app.models import BaseModel


class Upload(BaseModel):
    """
    A chunked upload. Stores chunks until used to create an artifact, etc.

    Fields:

        file (models.FileField): The uploaded file that is stored in a local file system.
        size (models.BigIntegerField): The size of the file in bytes.
    """

    file = models.FileField(
        null=False, max_length=255, storage=FileSystemStorage(location=settings.CHUNKED_UPLOAD_DIR)
    )
    size = models.BigIntegerField()

    def append(self, chunk, offset, sha256=None):
        """
        Append a chunk to an upload.

        Args:
            chunk (File): Binary file to append to the upload file.
            offset (int): First byte position to write chunk to.
        """
        if not self.file:
            self.file.save(str(self.pk), ContentFile(""))

        chunk_read = chunk.read()
        current_sha256 = hashlib.sha256(chunk_read).hexdigest()
        if sha256 and sha256 != current_sha256:
            raise serializers.ValidationError("Checksum does not match chunk upload.")

        with self.file.open(mode="r+b") as file:
            file.seek(offset)
            file.write(chunk_read)

        self.chunks.create(offset=offset, size=len(chunk))

    def delete(self, *args, **kwargs):
        """
        Deletes Upload model and the file associated with the model

        Args:
            args (list): list of positional arguments for Model.delete()
            kwargs (dict): dictionary of keyword arguments to pass to Model.delete()
        """
        super().delete(*args, **kwargs)
        self.file.delete(save=False)


class UploadChunk(BaseModel):
    """
    A chunk for an uploaded file.

    Fields:

        upload (models.ForeignKey): Upload this chunk belongs to.
        offset (models.BigIntegerField): Start of the chunk in bytes.
        size (models.BigIntegerField): Size of the chunk in bytes.
    """

    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name="chunks")
    offset = models.BigIntegerField()
    size = models.BigIntegerField()
