import hashlib
import os

from django.core.files.base import ContentFile
from django.db import models

from pulpcore.app.models import Model


class Upload(Model):
    """
    A chunked upload. Stores chunks until used to create an artifact, etc.

    Fields:

        file (models.FileField): The stored file.
        size (models.BigIntegerField): The size of the file in bytes.
        completed (models.DateTimeField): Time when the upload is committed
    """

    file = models.FileField(null=False, max_length=255)
    size = models.BigIntegerField()
    completed = models.DateTimeField(null=True)

    def append(self, chunk, offset):
        """
        Append a chunk to an upload.

        Args:
            chunk (File): Binary file to append to the upload file.
            offset (int): First byte position to write chunk to.
        """
        if not self.file:
            self.file.save(os.path.join('upload', str(self.pk)), ContentFile(''))

        with self.file.open(mode='r+b') as file:
            file.seek(offset)
            file.write(chunk.read())

        self.chunks.create(offset=offset, size=len(chunk))

    @property
    def sha256(self, rehash=False):
        if getattr(self, '_sha256', None) is None or rehash is True:
            sha256 = hashlib.sha256()
            with self.file.open(mode='rb') as file:
                for chunk in file.chunks():
                    sha256.update(chunk)
            self._sha256 = sha256.hexdigest()
        return self._sha256


class UploadChunk(Model):
    """
    A chunk for an uploaded file.

    Fields:

        upload (models.ForeignKey): Upload this chunk belongs to.
        offset (models.BigIntegerField): Start of the chunk in bytes.
        size (models.BigIntegerField): Size of the chunk in bytes.
    """

    upload = models.ForeignKey(Upload, on_delete=models.CASCADE, related_name='chunks')
    offset = models.BigIntegerField()
    size = models.BigIntegerField()
