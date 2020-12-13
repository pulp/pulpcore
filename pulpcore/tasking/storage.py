import os
import shutil
from gettext import gettext as _

from django.conf import settings
from rq.job import get_current_job


class WorkerDirectory:
    """
    The directory associated with a RQ worker.

    Path format: <root>/<worker-hostname>

    Attributes:
        _path (str): The absolute path.
    """

    # Directory permissions.
    MODE = 0o700

    @staticmethod
    def _worker_path(hostname):
        """
        Get the root directory path for a worker by hostname.

        Format: <root>/<worker-hostname>

        Args:
            hostname (str): The worker hostname.

        Returns:
            str: The absolute path to a worker's root directory.
        """
        root = settings.WORKING_DIRECTORY
        path = os.path.join(root, hostname)
        return path

    def __init__(self, hostname):
        """
        Args:
            hostname (str): The worker hostname.
        """
        self._path = self._worker_path(hostname)

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

        The directory is deleted and recreated when already exists.
        """

        def create():
            os.makedirs(self.path, mode=self.MODE)

        try:
            create()
        except FileExistsError:
            self.delete()
            create()

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
            shutil.rmtree(self.path)
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


class WorkingDirectory(WorkerDirectory):
    """
    RQ Job working directory.

    Path format: <worker-dir>/<task-id>

    Examples:
        >>>
        >>> with WorkingDirectory() as working_dir:
        >>>     # directory created.
        >>>     # process CWD = working_dir.path.
        >>>     ....
        >>> # directory deleted.
        >>> # process CWD restored.
        >>>
    """

    @staticmethod
    def _hostname():
        """
        The worker hostname.

        Returns:
            str: The worker hostname.

        Raises:
            RuntimeError: When used outside of an RQ task.
        """
        try:
            return get_current_job().origin
        except AttributeError:
            raise RuntimeError(_("May only be used within a Task."))

    @staticmethod
    def _task_id():
        """
        The current task ID.

        Returns:
            str: The current task ID.

        Raises:
            RuntimeError: When used outside of an RQ task.
        """
        try:
            return get_current_job().id
        except AttributeError:
            raise RuntimeError(_("May only be used within a Task."))

    def __init__(self):
        super().__init__(self._hostname())
        self._path = os.path.join(self._path, self._task_id())

    def __enter__(self):
        """
        Create the directory and set the CWD to the path.

        Returns:
            pulpcore.tasking.service.WorkingDirectory: self

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
