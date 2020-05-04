# coding=utf-8
"""Tests related to the tasking system."""
import unittest
from urllib.parse import urljoin

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import TASKS_PATH
from pulp_smash.pulp3.utils import delete_orphans, gen_remote, gen_repo, get_content_summary, sync
from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_FIXTURE_MANIFEST_URL,
    FILE_FIXTURE_SUMMARY,
    FILE_LARGE_FIXTURE_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import gen_file_remote
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class MultiResourceLockingTestCase(unittest.TestCase):
    """Verify multi-resourcing locking.

    This test targets the following issues:

    * `Pulp #3186 <https://pulp.plan.io/issues/3186>`_
    * `Pulp Smash #879 <https://github.com/pulp/pulp-smash/issues/879>`_
    """

    def test_all(self):
        """Verify multi-resourcing locking.

        Do the following:

        1. Create a repository, and a remote.
        2. Update the remote to point to a different url.
        3. Immediately run a sync. The sync should fire after the update and
           sync from the second url.
        4. Assert that remote url was updated.
        5. Assert that the number of units present in the repository is
           according to the updated url.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo["pulp_href"])

        body = gen_file_remote(url=FILE_LARGE_FIXTURE_MANIFEST_URL)
        remote = client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(client.delete, remote["pulp_href"])

        url = {"url": FILE_FIXTURE_MANIFEST_URL}
        client.patch(remote["pulp_href"], url)

        sync(cfg, remote, repo)

        repo = client.get(repo["pulp_href"])
        remote = client.get(remote["pulp_href"])
        self.assertEqual(remote["url"], url["url"])
        self.assertDictEqual(get_content_summary(repo), FILE_FIXTURE_SUMMARY)


class CancelTaskTestCase(unittest.TestCase):
    """Test to cancel a task in different states.

    This test targets the following issue:

    * `Pulp #3527 <https://pulp.plan.io/issues/3527>`_
    * `Pulp #3634 <https://pulp.plan.io/issues/3634>`_
    * `Pulp Smash #976 <https://github.com/pulp/pulp-smash/issues/976>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg, api.page_handler)

    def test_cancel_running_task(self):
        """Cancel a running task."""
        task = self.create_long_task()
        response = self.cancel_task(task)
        self.assertIsNone(response["finished_at"], response)
        self.assertEqual(response["state"], "canceled", response)

    def test_cancel_nonexistent_task(self):
        """Cancel a nonexistent task."""
        task_href = urljoin(TASKS_PATH, utils.uuid4() + "/")
        with self.assertRaises(HTTPError) as ctx:
            self.client.patch(task_href, json={"state": "canceled"})
        for key in ("not", "found"):
            self.assertIn(
                key, ctx.exception.response.json()["detail"].lower(), ctx.exception.response
            )

    def test_cancel_finished_task(self):
        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        repo["name"] = utils.uuid4()
        task_href = self.client.patch(repo["pulp_href"], json=repo)
        with self.assertRaises(HTTPError) as ctx:
            self.cancel_task(task_href)
        self.assertEqual(ctx.exception.response.status_code, 409)
        self.assertEqual(ctx.exception.response.json()["state"], "completed")

    def test_delete_running_task(self):
        """Delete a running task."""
        task = self.create_long_task()
        with self.assertRaises(HTTPError):
            self.client.delete(task["task"])

    def create_long_task(self):
        """Create a long task. Sync a repository with large files."""
        # to force the download of files.
        delete_orphans(self.cfg)

        repo = self.client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo["pulp_href"])

        body = gen_remote(url=FILE_LARGE_FIXTURE_MANIFEST_URL)
        remote = self.client.post(FILE_REMOTE_PATH, body)
        self.addCleanup(self.client.delete, remote["pulp_href"])

        # use code_handler to avoid wait to the task to be completed.
        return (
            self.client.using_handler(api.code_handler)
            .post(urljoin(repo["pulp_href"], "sync/"), {"remote": remote["pulp_href"]})
            .json()
        )

    def cancel_task(self, task):
        """Cancel a task."""
        return self.client.patch(task["task"], json={"state": "canceled"})
