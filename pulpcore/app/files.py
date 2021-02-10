import os
from gettext import gettext as _

from django.core.files.uploadedfile import TemporaryUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from pygtrie import StringTrie

from pulpcore.app import models
from pulpcore.app import pulp_hashlib


class PulpTemporaryUploadedFile(TemporaryUploadedFile):
    """
    A file uploaded to a temporary location in Pulp.
    """

    def __init__(self, name, content_type, size, charset, content_type_extra=None):
        self.hashers = {}
        for hasher in models.Artifact.DIGEST_FIELDS:
            self.hashers[hasher] = pulp_hashlib.new(hasher)
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
        instance = cls(name, "", file.size, "", "")
        instance.file = file
        data = file.read()

        # calling the method read() moves the file's pointer to the end of the file object,
        # thus, it is necessary to reset the file's pointer position back to 0 in case of
        # calling the method read() again from another place
        file.seek(0)

        for hasher in models.Artifact.DIGEST_FIELDS:
            instance.hashers[hasher].update(data)
        return instance


class HashingFileUploadHandler(TemporaryFileUploadHandler):
    """
    Upload handler that streams data into a temporary file.
    """

    def new_file(
        self,
        field_name,
        file_name,
        content_type,
        content_length,
        charset=None,
        content_type_extra=None,
    ):
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
        self.file = PulpTemporaryUploadedFile(
            file_name, content_type, 0, charset, content_type_extra
        )

    def receive_data_chunk(self, raw_data, start):
        self.file.write(raw_data)
        for hasher in models.Artifact.DIGEST_FIELDS:
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
            name = getattr(file, "name", None)
        self.name = name


def validate_file_paths(paths):
    """
    Check for valid POSIX paths (ie ones that aren't duplicated and don't overlap).

    Overlapping paths are where one path terminates inside another (e.g. a/b and a/b/c).

    This function will raise an exception at the first dupe or overlap it detects. We use a trie (or
    prefix tree) to keep track of which paths we've already seen.

    Args:
        paths (iterable of str): An iterable of strings each representing a relative path

    Raises:
        ValueError: If any path overlaps another
    """
    overlap_error = _("The path for file '{path}' overlaps: {conflicts}")

    path_trie = StringTrie(separator="/")
    for path in paths:
        if path in path_trie:
            # path duplicates a path already in the trie
            raise ValueError(_("Path is duplicated: {path}").format(path=path))

        if path_trie.has_subtrie(path):
            # overlap where path is 'a/b' and trie has 'a/b/c'
            conflicts = [item[0] for item in path_trie.items(prefix=path)]
            raise ValueError(overlap_error.format(path=path, conflicts=(", ").join(conflicts)))

        prefixes = list(path_trie.prefixes(path))
        if prefixes:
            # overlap where path is 'a/b/c' and trie has 'a/b'
            conflicts = [prefix.key for prefix in prefixes]
            raise ValueError(overlap_error.format(path=path, conflicts=(", ").join(conflicts)))

        # if there are no overlaps, add it to our trie and continue
        path_trie[path] = True
