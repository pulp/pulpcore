from rest_framework.response import Response
from rest_framework.reverse import reverse


class OperationPostponedResponse(Response):
    """
    An HTTP response class for returning 202 and a spawned task.

    This response object should be used by views that dispatch asynchronous tasks. The most common
    use case is for sync and publish operations. When JSON is requested, the response will look
    like the following::

        {
            "task": "/pulp/api/v3/tasks/735633bc-eb41-4737-b436-c7c6914f34b1/"
        }
    """

    def __init__(self, task, request):
        """
        Args:
            task (pulpcore.plugin.models.Task): A :class:`~pulpcore.plugin.models.Task` object
                used to generate the response.
            request (rest_framework.request.Request): Request used to generate the pulp_href urls
        """
        resp = {"task": reverse("tasks-detail", args=[task.pk], request=None)}
        super().__init__(data=resp, status=202)


class TaskGroupOperationResponse(Response):
    """
    An HTTP response class for returning 202 and a task group.

    This response object should be used by views that create a task group and dispatch one or more
    tasks for that group. When JSON is requested, the response will look like the following::

        {
            "task_group": "/pulp/api/v3/task-groups/735633bc-eb41-4737-b436-c7c6914f34b1/"
        }
    """

    def __init__(self, task_group, request):
        """
        Args:
            task_group (pulpcore.plugin.models.TaskGroup): A
                :class:`~pulpcore.plugin.models.TaskGroup` object used to generate the response.
            request (rest_framework.request.Request): Request used to generate the pulp_href urls
        """
        resp = {"task_group": reverse("task-groups-detail", args=[task_group.pk], request=None)}
        super().__init__(data=resp, status=202)
