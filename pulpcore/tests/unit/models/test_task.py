import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase

from pulpcore.app.models import ReservedResource, Task, TaskReservedResource, Worker


User = get_user_model()


class TaskTestCase(TestCase):
    @mock.patch("pulpcore.app.models.access_policy.get_current_authenticated_user")
    def test_delete_with_reserved_resources(self, mock_get_current_authenticated_user):
        """
        Tests that attempting to delete a task with reserved resources will raise
        a ProtectedError
        """
        test_user = User.objects.create(username="testuser")
        mock_get_current_authenticated_user.return_value = test_user
        # TODO: get rid of this once we can
        task = Task.objects.create(_resource_job_id=uuid.uuid4())
        worker = Worker.objects.create(name="test_worker")
        resource = ReservedResource.objects.create(resource="test", worker=worker)
        TaskReservedResource.objects.create(task=task, resource=resource)
        with self.assertRaises(ProtectedError):
            task.delete()
        task.release_resources()
        task.delete()
        test_user.delete()
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
