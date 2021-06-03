import unittest

from pulp_smash import config
from pulp_smash.pulp3.bindings import delete_orphans

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
        cls.paths = ["backupone/", "backuptwo/"]
        cls.paths_updated = ["backupone/", "anotherbackup/"]

    @classmethod
    def tearDownClass(cls):
        delete_orphans()

    def test_create_without_paths(self):
        """
        Basic ACS create.

        1. Try and fail to create ACS with remote with immediate policy
        2. Create ACS without paths and check it exists
        """
        remote_bad = self.file_remote_api.create(gen_file_remote())
        remote = self.file_remote_api.create(gen_file_remote(policy="on_demand"))
        self.addCleanup(self.file_remote_api.delete, remote_bad.pulp_href)
        self.addCleanup(self.file_remote_api.delete, remote.pulp_href)

        acs_data = {"name": "alternatecontentsource", "remote": remote_bad.pulp_href}
        with self.assertRaises(ApiException) as ctx:
            self.file_acs_api.create(acs_data)
        self.assertEqual(ctx.exception.status, 400)

        acs_data["remote"] = remote.pulp_href

        acs = self.file_acs_api.create(acs_data)
        self.addCleanup(self.file_acs_api.delete, acs.pulp_href)

        self.assertEqual(len(self.file_acs_api.list(name="alternatecontentsource").results), 1)

    def test_create_acs_with_paths(self):
        """ACS create with paths."""
        remote = self.file_remote_api.create(gen_file_remote(policy="on_demand"))
        self.addCleanup(self.file_remote_api.delete, remote.pulp_href)

        # one path is wrong, doesn't end with /
        acs_data = {
            "name": "alternatecontentsource",
            "remote": remote.pulp_href,
            "paths": ["goodpath/", "bad_path"],
        }

        with self.assertRaises(ApiException) as ctx:
            acs = self.file_acs_api.create(acs_data)
        self.assertEqual(ctx.exception.status, 400)

        # fix the path
        acs_data["paths"] = self.paths

        acs = self.file_acs_api.create(acs_data)
        self.addCleanup(self.file_acs_api.delete, acs.pulp_href)

        self.assertEqual(sorted(acs.paths), sorted(self.paths))

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
        self.file_acs_api.update(acs.pulp_href, {"name": new_name, "remote": acs.remote})
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(acs.name, new_name)

        # partial update name
        new_name = "new_acs"
        self.file_acs_api.partial_update(acs.pulp_href, {"name": new_name, "remote": acs.remote})
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(acs.name, new_name)

        # update paths
        self.file_acs_api.update(
            acs.pulp_href, {"name": acs.name, "remote": acs.remote, "paths": self.paths_updated}
        )
        acs = self.file_acs_api.read(acs.pulp_href)

        self.assertEqual(sorted(acs.paths), sorted(self.paths_updated))
