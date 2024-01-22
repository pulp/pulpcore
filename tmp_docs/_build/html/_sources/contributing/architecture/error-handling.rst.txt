.. _error-handling:

Error Handling
--------------

Errors in Tasks
***************

All uncaught exceptions in a task are treated as fatal exceptions. The task is then marked as
failed. The error traceback, description, and code are returned to the user under the
:attr:`~pulpcore.app.models.Task.error` attribute of the :class:`~pulpcore.app.models.Task`
object.

When raising exceptions `built-in Python Exceptions <https://docs.python.org/3/library/exceptions.html>`_
should be used if possible. :doc:`Coded Exceptions </contributing/platform-api/exceptions>` should be used for known error situations.
