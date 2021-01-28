"""Test that operations can be performed over tasks."""
import unittest

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import (
    BASE_DISTRIBUTION_PATH,
    P3_TASK_END_STATES,
    TASKS_PATH,
)
from pulp_smash.pulp3.utils import gen_repo, gen_distribution, get_content, modify_repo, sync
from requests import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.utils import set_up_module as setUpModule  # noqa:F401
from pulpcore.tests.functional.utils import skip_if
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote

_DYNAMIC_TASKS_ATTRS = ("finished_at",)
"""Task attributes that are dynamically set by Pulp, not set by a user."""


class TasksTestCase(unittest.TestCase):
    """Perform different operation over tasks.

    This test targets the following issues:

    * `Pulp #3144 <https://pulp.plan.io/issues/3144>`_
    * `Pulp #3527 <https://pulp.plan.io/issues/3527>`_
    * `Pulp Smash #754 <https://github.com/pulp/pulp-smash/issues/754>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.client = api.Client(config.get_config(), api.json_handler)
        cls.task = {}

    def test_01_create_task(self):
        """Create a task."""
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])
        attrs = {"description": utils.uuid4()}
        response = self.client.patch(repo["pulp_href"], attrs)
        self.task.update(self.client.get(response["task"]))

    @skip_if(bool, "task", False)
    def test_02_read_href(self):
        """Read a task by its pulp_href."""
        task = self.client.get(self.task["pulp_href"])
        for key, val in self.task.items():
            if key in _DYNAMIC_TASKS_ATTRS:
                continue
            with self.subTest(key=key):
                self.assertEqual(task[key], val, task)

    @skip_if(bool, "task", False)
    def test_02_read_href_with_specific_fields(self):
        """Read a task by its pulp_hrefproviding specific fields."""
        fields = ("pulp_href", "state", "worker")
        task = self.client.get(self.task["pulp_href"], params={"fields": ",".join(fields)})
        self.assertEqual(sorted(fields), sorted(task.keys()))

    @skip_if(bool, "task", False)
    def test_02_read_task_without_specific_fields(self):
        """Read a task by its href excluding specific fields."""
        # requests doesn't allow the use of != in parameters.
        url = "{}?exclude_fields=state".format(self.task["pulp_href"])
        task = self.client.get(url)
        self.assertNotIn("state", task.keys())

    @skip_if(bool, "task", False)
    def test_02_read_task_with_minimal_fields(self):
        """Read a task by its href filtering minimal fields."""
        task = self.client.get(self.task["pulp_href"], params={"minimal": True})
        response_fields = task.keys()
        self.assertNotIn("progress_reports", response_fields)
        self.assertNotIn("parent_task", response_fields)
        self.assertNotIn("error", response_fields)

    @skip_if(bool, "task", False)
    def test_02_read_invalid_worker(self):
        """Read a task using an invalid worker name."""
        with self.assertRaises(HTTPError):
            self.filter_tasks({"worker": utils.uuid4()})

    @skip_if(bool, "task", False)
    def test_02_read_valid_worker(self):
        """Read a task using a valid worker name."""
        page = self.filter_tasks({"worker": self.task["worker"]})
        self.assertNotEqual(len(page["results"]), 0, page["results"])

    def test_02_read_invalid_date(self):
        """Read a task by an invalid date."""
        with self.assertRaises(HTTPError):
            self.filter_tasks({"finished_at": utils.uuid4(), "started_at": utils.uuid4()})

    @skip_if(bool, "task", False)
    def test_02_read_valid_date(self):
        """Read a task by a valid date."""
        page = self.filter_tasks({"started_at": self.task["started_at"]})
        self.assertGreaterEqual(len(page["results"]), 1, page["results"])

    @skip_if(bool, "task", False)
    def test_02_search_task_by_name(self):
        """Search Task by its name.

        This test targets the following issue:

        * `Pulp #4230 <https://pulp.plan.io/issues/4230>`_

        Do the following:

        1. Assert that task has a field name, and that this field is not empty.
        2. Filter the tasks by name.
        3. Assert the created task is included on the search results.
        """
        # step 1
        self.assertIsNotNone(self.task.get("name"))
        # step 2
        search_results = self.filter_tasks({"name": self.task["name"]})
        # step 3
        self.assertIn(self.task, search_results["results"])

    def test_02_search_by_invalid_name(self):
        """Search passing invalid name and assert nothing is returned."""
        search_results = self.filter_tasks({"name": "this-is-not-a-task-name"})
        self.assertEqual(search_results["count"], 0)
        self.assertEqual(len(search_results["results"]), 0)

    @skip_if(bool, "task", False)
    def test_03_delete_tasks(self):
        """Delete a task."""
        # If this assertion fails, then either Pulp's tasking system or Pulp
        # Smash's code for interacting with the tasking system has a bug.
        self.assertIn(self.task["state"], P3_TASK_END_STATES)
        self.client.delete(self.task["pulp_href"])
        with self.assertRaises(HTTPError):
            self.client.get(self.task["pulp_href"])

    def filter_tasks(self, criteria):
        """Filter tasks based on the provided criteria."""
        return self.client.get(TASKS_PATH, params=criteria)


class FilterTaskCreatedResourcesTestCase(unittest.TestCase):
    """Perform filtering over the task's field created_resources.

    This test targets the following issue:

    * `Pulp #5180 <https://pulp.plan.io/issues/5180>`_
    """

    def test_read_fields_created_resources_only(self):
        """Read created resources from the requested fields."""
        client = api.Client(config.get_config(), api.page_handler)
        distribution_path = "{}file/file/".format(BASE_DISTRIBUTION_PATH)
        response = client.post(distribution_path, gen_distribution())

        task = client.get(response["task"])
        self.addCleanup(client.delete, task["created_resources"][0])

        filtered_task = client.get(task["pulp_href"], params={"fields": "created_resources"})

        self.assertEqual(len(filtered_task), 1, filtered_task)

        self.assertEqual(
            task["created_resources"], filtered_task["created_resources"], filtered_task
        )


class FilterTaskResourcesTestCase(unittest.TestCase):
    """Perform filtering over reserved resources.

    This test targets the following issue:
    * `Pulp #5120 <https://pulp.plan.io/issues/5120>`_

    Perform filtering for contents of created resources.

    This test targets the following issue:
    * `Pulp #4931 <https://pulp.plan.io/issues/4931>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)
        cls.remote = cls.client.post(FILE_REMOTE_PATH, gen_file_remote())
        cls.repository = cls.client.post(FILE_REPO_PATH, gen_repo())
        response = sync(cls.cfg, cls.remote, cls.repository)
        cls.created_repo_version = response["pulp_href"]
        cls.repository = cls.client.get(cls.repository["pulp_href"])
        for file_content in get_content(cls.repository)[FILE_CONTENT_NAME]:
            modify_repo(cls.cfg, cls.repository, remove_units=[file_content])
        attrs = {"description": utils.uuid4()}
        response = cls.client.patch(cls.repository["pulp_href"], attrs)
        cls.repo_update_task = cls.client.get(response["task"])

    @classmethod
    def tearDownClass(cls):
        """Clean created resources."""
        cls.client.delete(cls.repository["pulp_href"])
        cls.client.delete(cls.remote["pulp_href"])
        cls.client.delete(cls.repo_update_task["pulp_href"])

    def test_01_filter_tasks_by_reserved_resources(self):
        """Filter all tasks by a particular reserved resource."""
        filter_params = {
            "reserved_resources_record": self.repo_update_task["reserved_resources_record"][0]
        }
        results = self.client.get(TASKS_PATH, params=filter_params)
        self.assertEqual(len(results), 5, results)
        self.assertEqual(self.repo_update_task, results[0], results)

    def test_02_filter_tasks_by_non_existing_resources(self):
        """Filter all tasks by a non-existing reserved resource."""
        filter_params = {"reserved_resources_record": "a_resource_should_be_never_named_like_this"}
        with self.assertRaises(HTTPError):
            self.client.get(TASKS_PATH, params=filter_params)

    def test_03_filter_tasks_by_created_resources(self):
        """Filter all tasks by a particular created resource."""
        filter_params = {"created_resources": self.created_repo_version}
        results = self.client.get(TASKS_PATH, params=filter_params)
        self.assertEqual(len(results), 1, results)
        self.assertEqual([self.created_repo_version], results[0]["created_resources"], results)

    def test_04_filter_tasks_by_non_existing_resources(self):
        """Filter all tasks by a non-existing reserved resource."""
        filter_params = {"created_resources": "a_resource_should_be_never_named_like_this"}
        with self.assertRaises(HTTPError):
            self.client.get(TASKS_PATH, params=filter_params)
