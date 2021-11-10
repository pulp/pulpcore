"""
Tests task-purge functionality.
"""
from datetime import datetime, timedelta, timezone

from pulpcore.client.pulpcore import (
    ApiClient,
    ApiException,
    Purge,
    TasksApi,
)
from pulpcore.client.pulp_file import (
    RemotesFileApi,
    RepositoriesFileApi,
    RepositorySyncURL,
)

from pulpcore.constants import TASK_STATES, TASK_FINAL_STATES

from pulp_smash import config
from pulp_smash.pulp3.bindings import (
    monitor_task,
    PulpTestCase,
    PulpTaskError,
)
from .utils import gen_file_remote, gen_repo, gen_file_client, gen_user, del_user

TOMORROW_STR = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")


class TaskPurgeTestCase(PulpTestCase):
    """
    Test task-purge functionality.
    """

    def _task_summary(self):
        """
        Summary of number of tasks in all known task-states.
        :return: tuple of (total-tasks, Dict(state: count))
        """
        summary = {}
        total = 0
        final_total = 0
        for state in TASK_STATES.__dict__.values():
            response = self.task_api.list(state=state)
            summary[state] = response.count
            total += summary[state]
            final_total += summary[state] if state in TASK_FINAL_STATES else 0
        return total, final_total, summary

    def _purge_report_total(self, task):
        for report in task.progress_reports:
            if report.code == "purge.tasks.total":
                return report.total
        self.fail("NO PURGE_TASKS_TOTAL?!?")

    def _purge_report_check(self, task):
        subobj_total = 0
        total = 0
        for report in task.progress_reports:
            if report["code"] != "purge.tasks.total":
                total = report.total
            else:
                subobj_total += report.total
        self.assertEqual(total, subobj_total)

    def _check_delete_report(self, task, expected):
        # Make sure we reported the deletion
        for report in task.progress_reports:
            if report.code == "purge.tasks.key.core.Task":
                self.assertEqual(report.total, expected)
                break
        else:
            self.fail("NO core.Task DELETIONS?!?")

    @classmethod
    def setUpClass(cls):
        """Create repos, remotes, and api-clients for all tests."""
        cls.cfg = config.get_config()
        cls.client = ApiClient(configuration=cls.cfg.get_bindings_config())
        cls.task_api = TasksApi(cls.client)

        cls.file_client = gen_file_client()
        cls.remote_api = RemotesFileApi(cls.file_client)
        cls.repo_api = RepositoriesFileApi(cls.file_client)

        cls.good_remote = cls.remote_api.create(gen_file_remote(policy="on_demand"))
        cls.good_repo = cls.repo_api.create(gen_repo())
        cls.good_sync_data = RepositorySyncURL(remote=cls.good_remote.pulp_href)

        cls.bad_remote = cls.remote_api.create(
            gen_file_remote(
                "https://fixtures.pulpproject.org/THEREISNOFILEREPOHERE/", policy="on_demand"
            )
        )
        cls.bad_repo = cls.repo_api.create(gen_repo())
        cls.bad_sync_data = RepositorySyncURL(remote=cls.bad_remote.pulp_href)

    @classmethod
    def tearDownClass(cls) -> None:
        """Cleanup repos and remotes. Do the best we can, ignore any errors."""
        try:
            cls.remote_api.delete(cls.bad_remote.pulp_href)
        except:  # noqa
            pass
        try:
            cls.remote_api.delete(cls.good_remote.pulp_href)
        except:  # noqa
            pass
        try:
            cls.repo_api.delete(cls.bad_repo.pulp_href)
        except:  # noqa
            pass
        try:
            cls.repo_api.delete(cls.good_repo.pulp_href)
        except:  # noqa
            pass

    def setUp(self) -> None:
        """
        Give us tasks to operate on, and a summary of tasks before we got here.

        Sets up 1 completed sync, 1 failed.
        """
        self.pre_total, self.pre_final, self.pre_summary = self._task_summary()

        # good sync
        sync_response = self.repo_api.sync(self.good_repo.pulp_href, self.good_sync_data)
        task = monitor_task(sync_response.task)
        self.assertEqual(task.state, "completed")
        self.completed_sync_task = task

        # bad sync
        sync_response = self.repo_api.sync(self.bad_repo.pulp_href, self.bad_sync_data)
        with self.assertRaises(PulpTaskError):
            monitor_task(sync_response.task)
        task = self.task_api.read(sync_response.task)
        self.assertEqual(task.state, "failed")
        self.failed_sync_task = task

        self.post_total, self.post_final, self.post_summary = self._task_summary()
        self.assertEqual(self.post_total, (self.pre_total + 2))
        self.assertEqual(self.post_final, (self.pre_final + 2))

    def test_purge_before_time(self):
        """Purge that should find no tasks to delete."""
        dta = Purge(finished_before="1970-01-01T00:00")
        response = self.task_api.purge(dta)
        task = monitor_task(response.task)
        new_total, new_final, new_summary = self._task_summary()
        # Should have all tasks remaining (2 completed, 1 failed)
        self.assertEqual(self.pre_total + 3, new_total)
        # Should show we report having purged no tasks
        self.assertEqual(self._purge_report_total(task), 0)

    def test_purge_defaults(self):
        """Purge using defaults (finished_before=30-days-ago, state=completed)"""
        dta = Purge()
        response = self.task_api.purge(dta)
        monitor_task(response.task)

        # default is "completed before 30 days ago" - so both sync tasks should still exist
        # Make sure good sync-task still exists
        self.task_api.read(self.completed_sync_task.pulp_href)

        # Make sure the failed sync still exists
        self.task_api.read(self.failed_sync_task.pulp_href)

    def test_purge_all(self):
        """Purge all tasks in any 'final' state."""
        states = list(TASK_FINAL_STATES)
        dta = Purge(finished_before=TOMORROW_STR, states=states)
        response = self.task_api.purge(dta)
        task = monitor_task(response.task)
        new_total, new_final, new_summary = self._task_summary()
        self.assertEqual(1, new_final)  # The purge-task is the only final-task left

        # Make sure good sync-task is gone
        with self.assertRaises(ApiException):
            self.task_api.read(self.completed_sync_task.pulp_href)

        # Make sure failed sync-task is gone
        with self.assertRaises(ApiException):
            self.task_api.read(self.failed_sync_task.pulp_href)

        # Make sure we reported the deletions
        self._check_delete_report(task, self.pre_final + 2)

    def test_purge_leave_one(self):
        """Arrange to leave one task unscathed."""
        # Leave only the failed sync
        dta = Purge(finished_before=self.failed_sync_task.finished_at)
        response = self.task_api.purge(dta)
        task = monitor_task(response.task)

        # Make sure good sync-task is gone
        with self.assertRaises(ApiException):
            self.task_api.read(self.completed_sync_task.pulp_href)

        # Make sure the failed sync still exists
        self.task_api.read(self.failed_sync_task.pulp_href)

        # Make sure we reported the task-deletion
        self._check_delete_report(task, self.pre_summary["completed"] + 1)

    def test_purge_only_failed(self):
        """Purge all failed tasks only."""
        dta = Purge(finished_before=TOMORROW_STR, states=["failed"])
        response = self.task_api.purge(dta)
        monitor_task(response.task)
        # completed sync-task should exist
        self.task_api.read(self.completed_sync_task.pulp_href)

        # failed should not exist
        with self.assertRaises(ApiException):
            self.task_api.read(self.failed_sync_task.pulp_href)

    def test_bad_date(self):
        """What happens if you use a bad date format?"""
        dta = Purge(finished_before="THISISNOTADATE")
        with self.assertRaises(ApiException):
            self.task_api.purge(dta)

    def test_bad_state(self):
        """What happens if you specify junk for a state?"""
        dta = Purge(finished_before=TOMORROW_STR, states=["BAD STATE"])
        with self.assertRaises(ApiException):
            self.task_api.purge(dta)

    def test_not_final_state(self):
        """What happens if you use a valid state that isn't a 'final' one?"""
        dta = Purge(finished_before=TOMORROW_STR, states=["running"])
        with self.assertRaises(ApiException):
            self.task_api.purge(dta)


class TaskPurgeUserPermsTestCase(PulpTestCase):
    """
    Test task-purge is correctly protected by user-perms.

    Create new-user
    Sync as admin
    Purge as new-user, sync-task should NOT be deleted
    """

    @classmethod
    def setUpClass(cls):
        """Create repos, remotes, and api-clients for all tests."""
        cls.cfg = config.get_config()
        cls.client = ApiClient(configuration=cls.cfg.get_bindings_config())
        file_client = gen_file_client()
        cls.admin_info = {
            "task_api": TasksApi(cls.client),
            "file_client": file_client,
            "remote_api": RemotesFileApi(file_client),
            "repo_api": RepositoriesFileApi(file_client),
        }
        cls.admin_info["a_remote"] = cls.admin_info["remote_api"].create(
            gen_file_remote(policy="on_demand")
        )
        cls.admin_info["a_repo"] = cls.admin_info["repo_api"].create(gen_repo())
        cls.admin_info["sync_data"] = RepositorySyncURL(remote=cls.admin_info["a_remote"].pulp_href)

        cls.new_user = gen_user()
        file_client = gen_file_client()
        cls.user_info = {
            "task_api": TasksApi(cls.client),
            "file_client": file_client,
            "remote_api": RemotesFileApi(file_client),
            "repo_api": RepositoriesFileApi(file_client),
        }
        cls.user_info["a_remote"] = cls.user_info["remote_api"].create(
            gen_file_remote(policy="on_demand")
        )
        cls.user_info["a_repo"] = cls.user_info["repo_api"].create(gen_repo())
        cls.user_info["sync_data"] = RepositorySyncURL(remote=cls.user_info["a_remote"].pulp_href)

    @classmethod
    def tearDownClass(cls) -> None:
        """Cleanup repos and remotes."""
        cls.admin_info["remote_api"].delete(cls.admin_info["a_remote"].pulp_href)
        cls.admin_info["repo_api"].delete(cls.admin_info["a_repo"].pulp_href)
        cls.user_info["remote_api"].delete(cls.user_info["a_remote"].pulp_href)
        cls.user_info["repo_api"].delete(cls.user_info["a_repo"].pulp_href)
        del_user(cls.new_user)

    def testUserCannotPurge(self) -> None:
        """
        Test that purge does NOT purge tasks NOT OWNED by caller.
        """
        # Sync as admin
        sync_response = self.admin_info["repo_api"].sync(
            self.admin_info["a_repo"].pulp_href, self.admin_info["sync_data"]
        )
        task = monitor_task(sync_response.task)
        self.assertEqual(task.state, "completed")

        # Purge as user
        states = list(TASK_FINAL_STATES)
        dta = Purge(finished_before=TOMORROW_STR, states=states)
        response = self.user_info["task_api"].purge(dta)
        task = monitor_task(response.task)

        # Make sure sync-task (executed by admin) still exists
        self.admin_info["task_api"].read(task.pulp_href)

    def testUserCanPurge(self) -> None:
        """
        Test that purge DOES purge tasks owned by caller.
        """
        # Sync as user
        sync_response = self.user_info["repo_api"].sync(
            self.user_info["a_repo"].pulp_href, self.user_info["sync_data"]
        )
        sync_task = monitor_task(sync_response.task)
        self.assertEqual(sync_task.state, "completed")

        # Purge as user
        states = list(TASK_FINAL_STATES)
        dta = Purge(finished_before=TOMORROW_STR, states=states)
        response = self.user_info["task_api"].purge(dta)
        monitor_task(response.task)

        # Make sure task DOES NOT exist
        with self.assertRaises(ApiException):
            self.admin_info["task_api"].read(sync_task.pulp_href)

    def testAdminCanPurge(self) -> None:
        """
        Test that admin can ALWAYS purge.
        """
        # Sync as user
        sync_response = self.user_info["repo_api"].sync(
            self.user_info["a_repo"].pulp_href, self.user_info["sync_data"]
        )
        sync_task = monitor_task(sync_response.task)
        self.assertEqual(sync_task.state, "completed")

        # Purge as ADMIN
        states = list(TASK_FINAL_STATES)
        dta = Purge(finished_before=TOMORROW_STR, states=states)
        response = self.admin_info["task_api"].purge(dta)
        monitor_task(response.task)

        # Make sure task DOES NOT exist
        with self.assertRaises(ApiException):
            self.admin_info["task_api"].read(sync_task.pulp_href)
