"""Tests that perform actions over artifacts."""
import hashlib
import itertools
import os
import unittest

from aiohttp.client_exceptions import ClientResponseError

from pulpcore.tests.suite import api, cli, config, utils
from pulpcore.tests.suite.bindings import delete_orphans
from pulpcore.tests.suite.constants import ARTIFACTS_PATH


FILE_URL = "https://fixtures.pulpproject.org/file/1.iso"


class ArtifactTestCase(unittest.TestCase):
    """Create an artifact by uploading a file.

    This test targets the following issues:

    * `Pulp #2843 <https://pulp.plan.io/issues/2843>`_
    * `Pulp Smash #726 <https://github.com/pulp/pulp-smash/issues/726>`_
    """

    @classmethod
    def setUpClass(cls):
        """Delete orphans and create class-wide variables."""
        cfg = config.get_config()
        delete_orphans()
        cls.client = api.Client(cfg, api.json_handler)
        cls.file = utils.http_get(FILE_URL)
        cls.file_sha256 = hashlib.sha256(cls.file).hexdigest()
        cls.file_size = len(cls.file)

    def test_upload_valid_attrs(self):
        """Upload a file, and provide valid attributes.

        For each possible combination of ``sha256`` and ``size`` (including
        neither), do the following:

        1. Upload a file with the chosen combination of attributes.
        2. Verify that an artifact has been created, and that it has valid
           attributes.
        3. Delete the artifact, and verify that its attributes are
           inaccessible.
        """
        file_attrs = {"sha256": self.file_sha256, "size": str(self.file_size)}
        for i in range(len(file_attrs) + 1):
            for keys in itertools.combinations(file_attrs, i):
                data = {key: file_attrs[key] for key in keys}
                data["file"] = self.file
                with self.subTest(data=data):
                    self._do_upload_valid_attrs(data)

    def test_upload_empty_file(self):
        """Upload an empty file.

        For each possible combination of ``sha256`` and ``size`` (including
        neither), do the following:

        1. Upload a file with the chosen combination of attributes.
        2. Verify that an artifact has been created, and that it has valid
           attributes.
        3. Delete the artifact, and verify that its attributes are
           inaccessible.
        """
        empty_file = b""
        file_attrs = {"sha256": hashlib.sha256(empty_file).hexdigest(), "size": "0"}
        for i in range(len(file_attrs) + 1):
            for keys in itertools.combinations(file_attrs, i):
                data = {key: file_attrs[key] for key in keys}
                data["file"] = empty_file
                with self.subTest(data=data):
                    self._do_upload_valid_attrs(data)

    def _do_upload_valid_attrs(self, data):
        """Upload a file with the given attributes."""
        artifact = self.client.post(ARTIFACTS_PATH, data=data)
        # assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain "md5"
        self.assertTrue(artifact["md5"] is None, "MD5 {}".format(artifact["md5"]))
        self.addCleanup(self.client.delete, artifact["pulp_href"])
        read_artifact = self.client.get(artifact["pulp_href"])
        # assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain "md5"
        self.assertTrue(read_artifact["md5"] is None)
        for key, val in artifact.items():
            with self.subTest(key=key):
                self.assertEqual(read_artifact[key], val)
        self.doCleanups()
        with self.assertRaises(ClientResponseError) as cm:
            self.client.get(artifact["pulp_href"])

        assert cm.exception.status == 404

    def test_upload_invalid_attrs(self):
        """Upload a file, and provide invalid attributes.

        For each possible combination of ``sha256`` and ``size`` (except for
        neither), do the following:

        1. Upload a file with the chosen combination of attributes. Verify that
           an error is returned.
        2. Verify that no artifacts exist in Pulp whose attributes match the
           file that was unsuccessfully uploaded.
        """
        file_attrs = {"sha256": utils.uuid4(), "size": str(self.file_size + 1)}
        for i in range(1, len(file_attrs) + 1):
            for keys in itertools.combinations(file_attrs, i):
                data = {key: file_attrs[key] for key in keys}
                with self.subTest(data=data):
                    self._do_upload_invalid_attrs(data)

    def _do_upload_invalid_attrs(self, data):
        """Upload a file with the given attributes."""
        with self.assertRaises(ClientResponseError) as cm:
            self.client.post(ARTIFACTS_PATH, data=data)
        assert cm.exception.code == 400
        for artifact in self.client.get(ARTIFACTS_PATH)["results"]:
            self.assertNotEqual(artifact["sha256"], self.file_sha256)

    def test_upload_md5(self):
        """Attempt to upload a file using an MD5 checksum.

        Assumes ALLOWED_CONTENT_CHECKSUMS does NOT contain ``md5``
        """
        file_attrs = {"md5": utils.uuid4(), "size": str(self.file_size), "file": self.file}
        with self.assertRaises(ClientResponseError):
            self.client.post(ARTIFACTS_PATH, data=file_attrs)

    def test_upload_mixed_attrs(self):
        """Upload a file, and provide both valid and invalid attributes.

        Do the following:

        1. Upload a file and provide both an ``sha256`` and a ``size``. Let one
           be valid, and the other be valid. Verify that an error is returned.
        2. Verify that no artifacts exist in Pulp whose attributes match the
           file that was unsuccessfully uploaded.
        """
        invalid_data = (
            {"sha256": self.file_sha256, "size": str(self.file_size + 1)},
            {"sha256": utils.uuid4(), "size": str(self.file_size)},
        )
        for data in invalid_data:
            with self.subTest(data=data):
                self._do_upload_invalid_attrs(data)


class ArtifactsDeleteFileSystemTestCase(unittest.TestCase):
    """Delete an artifact, it is removed from the filesystem.

    This test targets the following issues:

    * `Pulp #3508 <https://pulp.plan.io/issues/3508>`_
    * `Pulp Smash #908 <https://github.com/pulp/pulp-smash/issues/908>`_
    """

    def test_all(self):
        """Delete an artifact, it is removed from the filesystem.

        Do the following:

        1. Create an artifact, and verify it is present on the filesystem.
        2. Delete the artifact, and verify it is absent on the filesystem.
        """
        cfg = config.get_config()
        cli_client = cli.Client(cfg)
        storage = utils.get_pulp_setting(cli_client, "DEFAULT_FILE_STORAGE")
        if storage != "pulpcore.app.models.storage.FileSystem":
            self.skipTest("this test only works for filesystem storage")
        media_root = utils.get_pulp_setting(cli_client, "MEDIA_ROOT")

        api_client = api.Client(cfg, api.json_handler)

        # create
        data = {"file": utils.http_get(FILE_URL)}
        artifact = api_client.post(ARTIFACTS_PATH, data=data)
        self.addCleanup(api_client.delete, artifact["pulp_href"])
        cmd = ("ls", os.path.join(media_root, artifact["file"]))
        cli_client.run(cmd, sudo=True)

        # delete
        self.doCleanups()
        with self.assertRaises(cli.CalledProcessError):
            cli_client.run(cmd, sudo=True)
