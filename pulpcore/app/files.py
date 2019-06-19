import hashlib
import os

from django.core.files.uploadedfile import TemporaryUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler


class PulpTemporaryUploadedFile(TemporaryUploadedFile):
    """
    A file uploaded to a temporary location in Pulp.
    """

    def __init__(self, name, content_type, size, charset, content_type_extra=None):
        self.hashers = {}
        for hasher in hashlib.algorithms_guaranteed:
            self.hashers[hasher] = getattr(hashlib, hasher)()
        super().__init__(name, content_type, size, charset, content_type_extra)

    @classmethod
    def from_file(cls, file):
        """
        Create a PulpTemporaryUploadedFile from a file system file

        Args:
            file (File): a filesystem file

        Returns:
            PulpTemporaryUploadedFile: instantiated instance from file
        """
        name = os.path.basename(file.name)
        instance = cls(name, '', file.size, '', '')
        instance.file = file
        data = file.read()
        for hasher in hashlib.algorithms_guaranteed:
            instance.hashers[hasher].update(data)
        return instance


class HashingFileUploadHandler(TemporaryFileUploadHandler):
    """
    Upload handler that streams data into a temporary file.
    """

    def new_file(self, field_name, file_name, content_type, content_length, charset=None,
                 content_type_extra=None):
        """
        Signal that a new file has been started.

        Args:
            field_name (str): Name of the model field that this file is associated with. This
                value is not used by this implementation of TemporaryFileUploadHandler.
            file_name (str): Name of file being uploaded.
            content_type (str): Type of file
            content_length (int): Size of the file being stored. This value is not used by this
                implementation of TemporaryFileUploadHandler.
            charset (str):
        """
        self.field_name = field_name
        self.content_length = content_length
        self.file = PulpTemporaryUploadedFile(file_name, content_type, 0, charset,
                                              content_type_extra)

    def receive_data_chunk(self, raw_data, start):
        self.file.write(raw_data)
        for hasher in hashlib.algorithms_guaranteed:
            self.file.hashers[hasher].update(raw_data)


class TemporaryDownloadedFile(TemporaryUploadedFile):
    """
    A temporary downloaded file.

    The FileSystemStorage backend treats this object the same as a TemporaryUploadedFile. The
    storage backend attempts to link the file to its final location. If the final location is on a
    different physical drive, the file is copied to its final destination.
    """

    def __init__(self, file, name=None):
        """
        A constructor that does not create a blank temporary file.

        The __init__ for TemporaryUploadedFile creates an empty temporary file. This constructor
        is designed to handle files that have already been written to disk.

        Args:
            file (file): An open file
            name (str): Name of the file
        """
        self.file = file
        if name is None:
            name = getattr(file, 'name', None)
        self.name = name
