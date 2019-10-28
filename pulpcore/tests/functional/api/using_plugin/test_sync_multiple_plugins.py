# # coding=utf-8
# """Tests related to multiple plugins."""
# import unittest
# from random import shuffle
# from unittest import SkipTest

# from pulp_smash import api, config
# from pulp_smash.pulp3.utils import (
#     gen_remote,
#     gen_repo,
#     get_added_content_summary,
#     get_content_summary,
#     get_removed_content_summary,
#     require_pulp_plugins,
#     sync,
# )

# from pulpcore.tests.functional.api.using_plugin.constants import (
#     DOCKER_CONTENT_BLOB_NAME,
#     DOCKER_CONTENT_MANIFEST_NAME,
#     DOCKER_CONTENT_TAG_NAME,
#     DOCKER_REMOTE_PATH,
#     DOCKER_UPSTREAM_NAME,
#     DOCKER_V2_FEED_URL,
#     FILE_CONTENT_NAME,
#     FILE_FIXTURE_MANIFEST_URL,
#     FILE_FIXTURE_SUMMARY,
#     FILE_REMOTE_PATH,
#     FILE_REPO_PATH,
#     RPM_ADVISORY_CONTENT_NAME,
#     RPM_FIXTURE_SUMMARY,
#     RPM_PACKAGE_CONTENT_NAME,
#     RPM_REMOTE_PATH,
#     RPM_REMOTE_PATH,
#     RPM_UNSIGNED_FIXTURE_URL,
# )
# from pulpcore.tests.functional.api.using_plugin.utils import set_up_module  # noqa


# def setUpModule():
#     """Conditions to skip tests.

#     Skip tests if not testing Pulp 3, or if either pulpcore, pulp_file
#     or pulp_rpm aren't installed.

#     refer :meth:`pulpcore.tests.functional.api.using_plugin.utils.set_up_module`
#     """
#     set_up_module()
#     require_pulp_plugins({'pulp_rpm'}, SkipTest)


# class SyncMultiplePlugins(unittest.TestCase):
#     """Sync repositories with the multiple plugins in the same repo."""

#     @classmethod
#     def setUpClass(cls):
#         """Create class-wide variables."""
#         cls.cfg = config.get_config()
#         cls.client = api.Client(cls.cfg, api.json_handler)

#     def test_mirror_sync(self):
#         """Attempt to sync multiple remotes from different plugins into the same repo.

#         This test targets the following issue: 5625

#         * `<https://pulp.plan.io/issues/5625>`_

#         This test does the following:

#         1. Create two repos.
#             a. File repo
#             b. RPM repo
#         2. Create two remotes
#             a. File remote
#             b. RPM remote
#         3. Sync the File repo with RPM remote.
#         4. Sync the RPM repo with File remote.
#         5. Verify that both syncs fail and no new repository versions are created.
#         """
#         # Step 1
#         file_repo = self.client.post(FILE_REPO_PATH, gen_repo())
#         self.addCleanup(self.client.delete, file_repo['pulp_href'])

#         rpm_repo = self.client.post(FILE_REPO_PATH, gen_repo())
#         self.addCleanup(self.client.delete, rpm_repo['pulp_href'])

#         # Step 2
#         file_remote = self.client.post(
#             FILE_REMOTE_PATH,
#             gen_remote(url=FILE_FIXTURE_MANIFEST_URL)
#         )
#         self.addCleanup(self.client.delete, file_remote['pulp_href'])

#         rpm_remote = self.client.post(
#             RPM_REMOTE_PATH,
#             gen_remote(url=RPM_UNSIGNED_FIXTURE_URL)
#         )
#         self.addCleanup(self.client.delete, rpm_remote['pulp_href'])

#         # Step 3
#         sync(self.cfg, rpm_remote, file_repo)
#         sync(self.cfg, file_remote, rpm_repo)

#     #     repo = self.client.get(repo['pulp_href'])
#     #     self.assertIsNotNone(repo['latest_version_href'])
#     #     self.assertDictEqual(
#     #         get_added_content_summary(repo),
#     #         RPM_FIXTURE_SUMMARY
#     #     )

#     #     # Step 4
#     #     sync(self.cfg, file_remote, repo, mirror=True)
#     #     repo = self.client.get(repo['pulp_href'])
#     #     self.assertIsNotNone(repo['latest_version_href'])
#     #     self.assertDictEqual(
#     #         get_added_content_summary(repo),
#     #         FILE_FIXTURE_SUMMARY
#     #     )

#     #     # Step 5
#     #     self.assertDictEqual(
#     #         get_content_summary(repo),
#     #         FILE_FIXTURE_SUMMARY
#     #     )
#     #     self.assertDictEqual(
#     #         get_removed_content_summary(repo),
#     #         RPM_FIXTURE_SUMMARY
#     #     )

#     # def test_sync_multiple_plugins(self):
#     #     """Sync a repo using remotes from different plugins.

#     #     This test targets the following issue:

#     #     `Pulp #4274 <https://pulp.plan.io/issues/4274>`_
#     #     """
#     #     repo = self.client.post(REPO_PATH, gen_repo())
#     #     self.addCleanup(self.client.delete, repo['pulp_href'])

#     #     rpm_remote = self.client.post(
#     #         RPM_REMOTE_PATH,
#     #         gen_remote(url=RPM_UNSIGNED_FIXTURE_URL)
#     #     )
#     #     self.addCleanup(self.client.delete, rpm_remote['pulp_href'])

#     #     file_remote = self.client.post(
#     #         FILE_REMOTE_PATH,
#     #         gen_remote(url=FILE_FIXTURE_MANIFEST_URL)
#     #     )
#     #     self.addCleanup(self.client.delete, file_remote['pulp_href'])

#     #     docker_remote = self.client.post(
#     #         DOCKER_REMOTE_PATH,
#     #         gen_remote(
#     #             url=DOCKER_V2_FEED_URL,
#     #             upstream_name=DOCKER_UPSTREAM_NAME
#     #         )
#     #     )
#     #     self.addCleanup(self.client.delete, docker_remote['pulp_href'])

#     #     remotes = [file_remote, docker_remote, rpm_remote]
#     #     shuffle(remotes)
#     #     for remote in remotes:
#     #         sync(self.cfg, remote, repo)

#     #     repo = self.client.get(repo['pulp_href'])

#     #     content_keys = sorted([
#     #         DOCKER_CONTENT_BLOB_NAME,
#     #         DOCKER_CONTENT_MANIFEST_NAME,
#     #         DOCKER_CONTENT_TAG_NAME,
#     #         FILE_CONTENT_NAME,
#     #         RPM_PACKAGE_CONTENT_NAME,
#     #         RPM_ADVISORY_CONTENT_NAME,
#     #     ])

#     #     content = get_content_summary(repo)

#     #     self.assertEqual(len(content), len(content_keys), content)

#     #     # Assert that all expected keys for different plugins are present.
#     #     self.assertEqual(
#     #         content_keys,
#     #         sorted([key for key in content.keys()]),
#     #         content
#     #     )

#     #     # Assert that sync the content was synced properly.
#     #     for value in content.values():
#     #         with self.subTest(value=value):
#     #             self.assertGreater(value, 0, content)
