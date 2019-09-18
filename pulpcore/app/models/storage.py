import errno
import os
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage


class FileSystem(FileSystemStorage):
    """
    Django's FileSystemStorage with modified save() behavior

    The FileSystemStorage backend provided by Django is designed to work with File,
    TemporaryUploadedFile, and InMemoryUploadedFile objects. The latter two inherit from the first.
    The type of File determines how the storage backend places it in its final destination. The
    Artifact upload API always uses a TemporaryUploadedFile, which writes the file to a temporary
    location on disk during the upload. Here is how FileSystemStorage saves a file to its
    destination for the two File types we are interested in:

    TemporaryUploadedFile
    ------------------------------
    1) is name available?
         2a) yes, os.rename()
                 3a) no exception, you are done
                 3b) exception, copy from source to destination using python and delete the original
         2b) no, append random characters to to the name and go back to 1

    File
    -----
    1) is name available?
         2a) yes, copy from source to destination using python
         2b) no, append random characters to to the name and go back to 1

    The behavior from 2b can result in duplicate files being created, but not associated with any
    Artifact. There is a race condition if the same file is being uploaded in two parallel
    requests. One of the requests will create the Artifact in /var/lib/pulp/artifact and then
    save it to the database. The second request will also create a file in
    /var/lib/pulp/artifacts, but it will have a random name. The database insert will fail due to
    uniqueness constraint and the user will receive a 400 error. No cleanup happens when this
    occurs.

    Here is how FileSystem saves a file to its destination for the two File types we are
    interested in:

    TemporaryUploadedFile
    ------------------------------
    1) is name available?
         2a) yes, os.rename()
                 3a) no exception, you are done
                 3b) exception, copy from source to destination using python and delete the original
         2b) no, the file already exists. keep the existing file in place.

    File
    -----
    1) is name available?
         2a) yes, copy from source to destination using python
         2b) no, the file already exists. keep the existing file in place.

    The difference between the two save() methods is in the behavior at 2b.

    The non-atomic nature of 3b makes it possible for corrupted Artifacts to be saved if
    /var/lib/pulp/tmp and /var/lib/pulp/artifact are on separate filesystems. An interrupted save()
    operation will result in a partial file being placed into /var/lib/pulp/artifact. In such
    situations, Pulp will not be able to replace the file with the correct version in the
    future and the user will have to manually remove the partial file.
    """

    def get_available_name(self, name, max_length=None):
        """
        Returns a filename if a file by that name does not exist

        Args:
            name (string): Requested file name
            max_length (int): Maximum length of the filename. Not used in this implementation.

        Returns:
            Name of the file.

        Raises:
            OSError if a file with requested name already exists.
        """
        if self.exists(name):
            raise OSError(errno.EEXIST, "File Exists")
        else:
            return name

    def save(self, name, content, max_length=None):
        """
        Saves the file if it doesn't already exist

        Args:
            name (str): Target path to which the file is copied.
            content (File): Source file object.
            max_length (int): Maximum supported length of file name.

        Returns:
            str: Final storage path.
        """
        if name is None:
            name = content.name

        if not hasattr(content, 'chunks'):
            content = File(content, name)

        try:
            name = self.get_available_name(name, max_length=max_length)
            return self._save(name, content)
        except OSError as e:
            if e.errno == errno.EEXIST:
                return name
            else:
                raise


def get_artifact_path(sha256digest):
    """
    Determine the absolute path where a file backing the Artifact should be stored.

    Args:
        sha256digest (str): sha256 digest of the file for the Artifact

    Returns:
        A string representing the absolute path where a file backing the Artifact should be
        stored
    """
    return os.path.join('artifact', sha256digest[0:2], sha256digest[2:])


def get_tls_path(model, name):
    """
    Determine storage location as: MEDIA_ROOT/tls/<model>/<id>/<name>.

    Args:
        model (pulpcore.app.models.Model): The model object.
        name (str): The (unused) input file path.

    Returns:
        str: An absolute (base) path
    """
    return os.path.join(
        settings.MEDIA_ROOT,
        'tls',
        type(model).__name__,
        str(uuid4()),
        name)
