"""
Django models related to progress reporting
"""
import datetime
import logging
from asgiref.sync import sync_to_async
from asyncio import CancelledError
from gettext import gettext as _

from django.db import models
from django.utils import timezone

from pulpcore.app.models import BaseModel, Task
from pulpcore.constants import TASK_CHOICES, TASK_STATES

_logger = logging.getLogger(__name__)

# number of ms between save() calls when _using_context_manager is set
BATCH_INTERVAL = 2000


class ProgressReport(BaseModel):
    """
    A model for all progress reporting.

    All progress reports have a message, state, and are related to a Task.

    Plugin writers should create these objects to show progress reporting of a single step or
    aspect of work which has a name and state. For example:

        >>> ProgressReport(
        >>>     message='Publishing files', code='publish', total=23
        >>> )  # default: state='waiting' and done=0

        >>> ProgressReport(
        >>>     message='Publishing files', code='publish', total=23, state='running'
        >>> )  # specify the state
        >>> ProgressReport(
        >>>     message='Publishing files', code='publish', total=23, done=16
        >>> )  # already completed 16

    Update the state to COMPLETED and save it:

        >>> progress_bar = ProgressReport(
        >>>     message='Publishing files', code='publish', total=23, state='running'
        >>> )
        >>> progress_bar.state = 'completed'
        >>> progress_bar.save()

    The ProgressReport() is a context manager that provides automatic state transitions and saving
    for the RUNNING CANCELED COMPLETED and FAILED states. The increment() method can be called in
    the loop as work is completed. When ProgressReport() is used as a context manager progress
    reporting is rate limited to every 500 milliseconds.
    Use it as follows:

        >>> progress_bar = ProgressReport(
        >>>     message='Publishing files', code='publish', total=len(files_iterator)
        >>> )
        >>> progress_bar.save()
        >>> with progress_bar:
        >>>     # progress_bar saved as 'running'
        >>>     for file in files_iterator:
        >>>         handle(file)
        >>>         progress_bar.increment()  # increments and saves
        >>> # progress_bar is saved as 'completed' if no exception or 'failed' otherwise

    A convenience method called iter() allows you to avoid calling increment() directly:

        >>> progress_bar = ProgressReport(
        >>>     message='Publishing files', code='publish', total=len(files_iterator)
        >>> )
        >>> progress_bar.save()
        >>> with progress_bar:
        >>>     for file in progress_bar.iter(files_iterator):
        >>>         handle(file)

    You can also use this short form which handles all necessary save() calls:

        >>> data = dict(message='Publishing files', code='publish', total=len(files_iterator))
        >>> with ProgressReport(**data) as pb:
        >>>     for file in pb.iter(files_iterator):
        >>>         handle(file)

    ProgressReport objects are associated with a Task and auto-discover and populate the task id
    when saved.

    When using threads to update a ProgressReport in parallel, it is recommended that all threads
    share the same in-memory instance. Django does not synchronize in-memory model instances, so
    multiple instances of a specific ProgressReport will diverge as they are written to from
    separate threads.

    Fields:

        message (models.TextField): short message for the progress update, typically
            shown to the user. (required)
        code (models.TextField): identifies the type of progress report
        state (models.TextField): The state of the progress update. Defaults to `WAITING`. This
            field uses a limited set of choices of field states. See `STATES` for possible states.
        total: (models.IntegerField) The total count of items to be handled
        done (models.IntegerField): The count of items already processed. Defaults to 0.
        suffix (models.TextField): Customizable suffix rendered with the progress report
            See `the docs <https://github.com/verigak/progress>`_. for more info.

    Relations:

        task: The task associated with this progress report. If left unset when save() is called
            it will be set to the current task_id.
    """

    message = models.TextField()
    code = models.CharField(max_length=36)
    state = models.TextField(choices=TASK_CHOICES, default=TASK_STATES.WAITING)

    total = models.IntegerField(null=True)
    done = models.IntegerField(default=0)

    task = models.ForeignKey("Task", related_name="progress_reports", on_delete=models.CASCADE)

    suffix = models.TextField(null=True)

    _using_context_manager = False
    _last_save_time = None

    def save(self, *args, **kwargs):
        """
        Auto-set the task_id if running inside a task

        If the task_id is already set it will not be updated. If it is unset and this is running
        inside of a task it will be auto-set prior to saving.

        args (list): positional arguments to be passed on to the real save
        kwargs (dict): keyword arguments to be passed on to the real save
        """
        now = timezone.now()

        if not self.task_id:
            self.task = Task.current()

        if self._using_context_manager and self._last_save_time:
            if now - self._last_save_time >= datetime.timedelta(milliseconds=BATCH_INTERVAL):
                super().save(*args, **kwargs)
                self._last_save_time = now
        else:
            super().save(*args, **kwargs)
            self._last_save_time = now

    asave = sync_to_async(save)

    def __enter__(self):
        """
        Saves the progress report state as RUNNING
        """
        self.state = TASK_STATES.RUNNING
        self.save()

        # Save needs occurs immediately so it is called before _using_context_manager is set
        self._using_context_manager = True
        return self

    async def __aenter__(self):
        """
        Async implementation of __enter__
        """
        self.state = TASK_STATES.RUNNING
        await self.asave()

        # Save needs occurs immediately so it is called before _using_context_manager is set
        self._using_context_manager = True
        return self

    def __exit__(self, type, value, traceback):
        """
        Update the progress report state to COMPLETED, CANCELED, or FAILED.

        If an exception occurs the progress report state is saved as:
        - CANCELED if the exception is `asyncio.CancelledError`
        - FAILED otherwise.

        The exception is not suppressed. If the context manager exited without
        exception the progress report state is saved as COMPLETED.

        See the context manager documentation for more info on __exit__ parameters
        """
        self._using_context_manager = False
        if type is None:
            self.state = TASK_STATES.COMPLETED
        elif type is CancelledError:
            self.state = TASK_STATES.CANCELED
        else:
            self.state = TASK_STATES.FAILED
        self.save()

    async def __aexit__(self, type, value, traceback):
        """
        Async implementation of __exit__

        Update the progress report state to COMPLETED, CANCELED, or FAILED.

        If an exception occurs the progress report state is saved as:
        - CANCELED if the exception is `asyncio.CancelledError`
        - FAILED otherwise.

        The exception is not suppressed. If the context manager exited without
        exception the progress report state is saved as COMPLETED.

        See the context manager documentation for more info on __exit__ parameters
        """
        self._using_context_manager = False
        if type is None:
            self.state = TASK_STATES.COMPLETED
        elif type is CancelledError:
            self.state = TASK_STATES.CANCELED
        else:
            self.state = TASK_STATES.FAILED
        await self.asave()

    def increment(self):
        """
        Increment done count and save the progress report.

        This will increment and save the self.done attribute which is useful to put into a loop
        processing items.
        """
        self.increase_by(1)

    aincrement = sync_to_async(increment)

    def increase_by(self, count):
        """
        Increase the done count and save the progress report.

        This will increment and save the self.done attribute which is useful to put into a loop
        processing items.
        """
        self.done += count
        if self.total:
            if self.done > self.total:
                _logger.warning(_("Too many items processed for ProgressReport %s") % self.message)
        self.save()

    aincrease_by = sync_to_async(increase_by)

    def iter(self, iter):
        """
        Iterate and automatically call increment().

            >>> progress_bar = ProgressReport(message='Publishing files', code='publish', total=23)
            >>> progress_bar.save()
            >>> for file in progress_bar.iter(files_iterator):
            >>>     handle(file)

        Args:
            iter (iterator): The iterator to loop through while incrementing

        Returns:
            generator of ``iter`` argument items
        """
        for x in iter:
            yield x
            self.increment()


class GroupProgressReport(BaseModel):
    """
    A model for all progress reporting in a Task Group.

    All progress reports have a message, code and are related to a Task Group.

    Once a Task Group is created, plugin writers should create these objects ahead.
    For example:

        >>> task_group = TaskGroup(description="Migration Sub-tasks")
        >>> task_group.save()
        >>> group_pr = GroupProgressReport(
        >>>     message="Repo migration",
        >>>     code="create.repo_version",
        >>>     task_group=task_group).save()

    Taks that will be executing certain work, and is part of a TaskGroup, will look for
    the Task group it belongs to and find appropriate progress report by its code and will
    update it accordingly.

    For example:

        >>> task_group = TaskGroup.current()
        >>> progress_repo = task_group.group_progress_reports.filter(code='create.repo_version')
        >>> progress_repo.update(done=F('done') + 1)

    To avoid race conditions/cache invalidation issues, this pattern needs to be used so that
    operations are performed directly inside the database:

    .update(done=F('done') + 1)

    See: https://docs.djangoproject.com/en/3.0/ref/models/expressions/#f-expressions
    Important: F() objects assigned to model fields persist after saving the model instance and
    will be applied on each save(). Do not use save() and use update() instead, otherwise
    refresh_from_db() should be called after each save()

    Fields:

        message (models.TextField): short message for the progress update, typically
            shown to the user. (required)
        code (models.TextField): identifies the type of progress report
        total: (models.IntegerField) The total count of items to be handled
        done (models.IntegerField): The count of items already processed. Defaults to 0.
        suffix (models.TextField): Customizable suffix rendered with the progress report
            See `the docs <https://github.com/verigak/progress>`_. for more info.

    Relations:

        task_group: The task group associated with this group progress report.

    """

    message = models.TextField()
    code = models.CharField(max_length=36)

    total = models.IntegerField(default=0)
    done = models.IntegerField(default=0)

    task_group = models.ForeignKey(
        "TaskGroup", related_name="group_progress_reports", on_delete=models.CASCADE
    )

    suffix = models.TextField(null=True)

    class Meta:
        unique_together = ("code", "task_group")
