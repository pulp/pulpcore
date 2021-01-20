import os
from uuid import uuid4

from django.conf import settings
from django.core.files import locks
from django.core.files.move import file_move_safe
from django.core.files.storage import FileSystemStorage


class FileSystem(FileSystemStorage):
    """
    Django's FileSystemStorage with modified _save() and get_available_name behaviors

    The _save() will check if the file is saved in MEDIA_ROOT first. If it is, a move is used. This
    will move all files created by the Downloaders and uploaded files from the user. If it is saved
    in-memory or outside of MEDIA_ROOT, the data is written in chunks to the new location.
    """

    def get_available_name(self, name, max_length=None):
        """
        Returns a filename for the file even if it already exists.

        Content adressable storage must be saved with the expected filename.

        Args:
            name (string): Requested file name
            max_length (int): Maximum length of the filename. Not used in this implementation.

        Returns:
            Name of the file.
        """
        return name

    def _save(self, name, content, max_length=None):
        """
        Create dirs to the destination, move the file if already in MEDIA_ROOT, or copy otherwise.

        Args:
            name (str): Target path to which the file is copied.
            content (File): Source file object.
            max_length (int): Maximum supported length of file name.

        Returns:
            str: Final storage path.
        """
        full_path = self.path(name)

        # Create any intermediate directories that do not exist.
        directory = os.path.dirname(full_path)
        try:
            if self.directory_permissions_mode is not None:
                # os.makedirs applies the global umask, so we reset it,
                # for consistency with file_permissions_mode behavior.
                old_umask = os.umask(0)
                try:
                    os.makedirs(directory, self.directory_permissions_mode, exist_ok=True)
                finally:
                    os.umask(old_umask)
            else:
                os.makedirs(directory, exist_ok=True)
        except FileExistsError:
            raise FileExistsError("%s exists and is not a directory." % directory)

        try:
            if hasattr(content, "temporary_file_path") and content.temporary_file_path().startswith(
                settings.MEDIA_ROOT
            ):
                file_move_safe(content.temporary_file_path(), full_path)
            else:
                # This is a normal uploaded file that we can stream.

                # The current umask value is masked out by os.open!
                fd = os.open(full_path, self.OS_OPEN_FLAGS, 0o666)
                _file = None
                try:
                    locks.lock(fd, locks.LOCK_EX)
                    for chunk in content.chunks():
                        if _file is None:
                            mode = "wb" if isinstance(chunk, bytes) else "wt"
                            _file = os.fdopen(fd, mode)
                        _file.write(chunk)
                finally:
                    locks.unlock(fd)
                    if _file is not None:
                        _file.close()
                    else:
                        os.close(fd)
        except FileExistsError:
            # It's a content addressable store so if the file is already in place we can do nothing
            pass

        if self.file_permissions_mode is not None:
            os.chmod(full_path, self.file_permissions_mode)

        # Store filenames with forward slashes, even on Windows.
        return str(name).replace("\\", "/")


def get_artifact_path(sha256digest):
    """
    Determine the absolute path where a file backing the Artifact should be stored.

    Args:
        sha256digest (str): sha256 digest of the file for the Artifact

    Returns:
        A string representing the absolute path where a file backing the Artifact should be
        stored
    """
    return os.path.join("artifact", sha256digest[:2], sha256digest[2:])


def get_temp_file_path(pulp_id):
    """
    Determine the absolute path where a file backing the PulpTemporaryFile should be stored.

    Args:
        pulp_id (uuid): An identifier identifying the file for the PulpTemporaryFile

    Returns:
        A string representing the absolute path where a file backing the PulpTemporaryFile should be
        stored
    """
    pulp_id_str = str(pulp_id)
    return os.path.join("tmp/files", pulp_id_str[:2], pulp_id_str[2:])


def get_upload_chunk_file_path(pulp_id):
    """
    Determine the relative path where a file backing an uploaded chunk should be stored.

    Args:
        pulp_id (uuid): An identifier identifying the file for UploadChunk
    Returns:
        A string representing the relative path where a file backing UploadChunk should be
        stored
    """
    return os.path.join(settings.CHUNKED_UPLOAD_DIR, str(pulp_id))


def get_tls_path(model, name):
    """
    Determine storage location as: MEDIA_ROOT/tls/<model>/<id>/<name>.

    Args:
        model (pulpcore.app.models.Model): The model object.
        name (str): The (unused) input file path.

    Returns:
        str: An absolute (base) path
    """
    return os.path.join(settings.MEDIA_ROOT, "tls", type(model).__name__, str(uuid4()), name)
