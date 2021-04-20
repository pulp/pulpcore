import os
import shutil

from django.conf import settings


class _WorkingDir:
    """
    A base class for temporary working directories.

    TODO: This is very similar to functionality already in the stdlib, why keep our own?

    https://docs.python.org/3/library/tempfile.html#tempfile.TemporaryDirectory
    """

    # Directory permissions.
    MODE = 0o700

    def __init__(self, path):
        """
        Args:
            path (str): The absolute directory path to use.
        """
        self._path = path

    @property
    def path(self):
        """
        The absolute path to the directory.

        Returns:
            str: The absolute directory path.
        """
        return self._path

    def create(self):
        """
        Create the directory.
        """
        os.makedirs(self.path, mode=self.MODE)

    def delete(self):
        """
        Delete the directory.

        On permission denied - an attempt is made to fix the
        permissions on the tree and the delete is retried.
        """
        try:
            self._delete()
        except PermissionError:
            self._set_permissions()
            self._delete()

    def _delete(self):
        """
        Helper method for delete
        """
        try:
            shutil.rmtree(self.path, ignore_errors=True)
        except FileNotFoundError:
            pass

    def _set_permissions(self):
        """
        Set appropriate permissions on the directory tree.
        """
        for path in os.walk(self.path):
            os.chmod(path[0], mode=self.MODE)

    def __str__(self):
        return self.path

    def __enter__(self):
        """
        Create the directory and set the CWD to the path.

        Returns: self

        Raises:
            OSError: On failure.
        """
        self.create()
        self._prev_dir = os.getcwd()
        os.chdir(self._path)
        return self

    def __exit__(self, *unused):
        """
        Delete the directory (tree) and restore the original CWD.
        """
        os.chdir(self._prev_dir)
        self.delete()


def get_worker_path(hostname):
    """
    Get the root directory path for a worker by hostname.

    Format: <root>/<worker-hostname>

    Args:
        hostname (str): The worker hostname.

    Returns:
        str: The absolute path to a worker's root directory.
    """
    return os.path.join(settings.WORKING_DIRECTORY, hostname)


class WorkerDirectory(_WorkingDir):
    """
    The directory associated with a RQ worker.

    Path format: <root>/<worker-hostname>
    """

    def __init__(self, hostname):
        """
        Args:
            hostname (str): The worker hostname.
        """
        self._path = get_worker_path(hostname)

    def create(self):
        """
        Create the directory.

        The directory is deleted and recreated when already exists.
        Only one of these should ever be held at a time for any individual worker.
        """
        try:
            super().create()
        except FileExistsError:
            self.delete()
            super().create()


class TaskWorkingDirectory(_WorkingDir):
    """
    RQ Job working directory.

    Path format: <worker-dir>/<task-id>/
    """

    def __init__(self, job):
        """
        Create a WorkingDirectory.

        Args:
            job (rq.Job): The RQ job to create a working directory for

        Raises:
            RuntimeError: When used outside of an RQ task.
        """
        self.hostname = job.origin
        self.task_id = job.id
        self.task_path = os.path.join(get_worker_path(self.hostname), self.task_id)
        super().__init__(self.task_path)
