import unittest

from pulp_smash import config
from pulp_smash.pulp3.bindings import delete_orphans, monitor_task

from pulpcore.client.pulp_file import AcsFileApi, RemotesFileApi
from pulpcore.client.pulp_file.exceptions import ApiException

from pulpcore.tests.functional.api.using_plugin.utils import (
    gen_file_client,
    gen_file_remote,
)


class AlternateContentSourceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Create class-wide variables.

        Variables 'paths' and 'paths_updated' are defined as strings.
        In same way data are send from user.
        """
        cls.cfg = config.get_config()
        cls.file_client = gen_file_client()
        cls.file_remote_api = RemotesFileApi(cls.file_client)
        cls.file_acs_api = AcsFileApi(cls.file_client)
        cls.paths = ["backupone/PULP_MANIFEST", "backuptwo/manifest"]
        cls.paths_updated = ["backupone/test", "anotherbackup/PULP_MANIFEST"]

    @classmethod
    def tearDownClass(cls):
        delete_orphans()

    def test_create(self):
        """
        Basic ACS create.

        1. Try and fail to create ACS with remote with immediate policy
        2. Create ACS and check it exists
        """
        remote_bad = self.file_remote_api.create(gen_file_remote())
        remote = self.file_remote_api.create(gen_file_remote(policy="on_demand"))
        self.addCleanup(self.file_remote_api.delete, remote_bad.pulp_href)
        self.addCleanup(self.file_remote_api.delete, remote.pulp_href)

        acs_data = {
            "name": "alternatecontentsource",
            "remote": remote_bad.pulp_href,
            "paths": self.paths,
        }
        with self.assertRaises(ApiException) as ctx:
            self.file_acs_api.create(acs_data)
        self.assertEqual(ctx.exception.status, 400)

        acs_data["remote"] = remote.pulp_href

        acs = self.file_acs_api.create(acs_data)
        self.addCleanup(self.file_acs_api.delete, acs.pulp_href)

        self.assertEqual(len(self.file_acs_api.list(name="alternatecontentsource").results), 1)

    def test_acs_update(self):
        """
        ACS update.

        Test of update name and paths.
        """
        remote = self.file_remote_api.create(gen_file_remote(policy="on_demand"))
        self.addCleanup(self.file_remote_api.delete, remote.pulp_href)

        acs_data = {
            "name": "alternatecontentsource",
            "remote": remote.pulp_href,
            "paths": self.paths,
        }
        acs = self.file_acs_api.create(acs_data)
        self.addCleanup(self.file_acs_api.delete, acs.pulp_href)

        # update name
        new_name = "acs"
        response = self.file_acs_api.update(acs.pulp_href, {"name": new_name, "remote": acs.remote})
        monitor_task(response.task)
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(acs.name, new_name)
        # assert paths were not silently removed during name update
        self.assertEqual(sorted(acs.paths), sorted(self.paths))

        # partial update name
        new_name = "new_acs"
        response = self.file_acs_api.partial_update(
            acs.pulp_href, {"name": new_name, "remote": acs.remote}
        )
        monitor_task(response.task)
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(acs.name, new_name)

        # update paths
        response = self.file_acs_api.update(
            acs.pulp_href, {"name": acs.name, "remote": acs.remote, "paths": self.paths_updated}
        )
        monitor_task(response.task)
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(sorted(acs.paths), sorted(self.paths_updated))
