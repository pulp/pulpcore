# coding=utf-8
"""Tests related to content upload."""
import os
import hashlib
import unittest
from random import shuffle
from urllib.parse import urljoin

from pulp_smash import api, cli, config
from pulp_smash.utils import http_get
from pulp_smash.exceptions import CalledProcessError
from pulp_smash.pulp3.constants import ARTIFACTS_PATH, UPLOAD_PATH, MEDIA_PATH

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CHUNKED_PART_1_URL,
    FILE_CHUNKED_PART_2_URL,
    FILE_TO_BE_CHUNKED_URL,
)
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class ChunkedUploadTestCase(unittest.TestCase):
    """Test upload of files in chunks.

    This test targets the following issues:

    * `Pulp #4197 <https://pulp.plan.io/issues/4197>`_
    * `Pulp #5092 <https://pulp.plan.io/issues/5092>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""

        cls.cfg = config.get_config()
        cls.cli_client = cli.Client(cls.cfg)
        cls.client = api.Client(cls.cfg)

        cls.file = http_get(FILE_TO_BE_CHUNKED_URL)
        cls.file_sha256 = hashlib.sha256(cls.file).hexdigest()
        cls.size_file = len(cls.file)

        cls.first_chunk = http_get(FILE_CHUNKED_PART_1_URL)
        cls.second_chunk = http_get(FILE_CHUNKED_PART_2_URL)

    def test_create_artifact(self):
        """Test creation of artifact using upload of files in chunks."""

        upload_request = self.upload_chunks()

        response = self.client.post(
            ARTIFACTS_PATH, {'upload': upload_request['_href']}
        )

        artifact = self.client.get(response['_href'])
        self.addCleanup(self.client.delete, artifact['_href'])

        self.assertEqual(artifact['sha256'], self.file_sha256, artifact)

    def test_delete_upload(self):
        """Test a deletion of an upload using upload of files in chunks."""

        upload_request = self.upload_chunks()

        # fetch a name of the upload from the corresponding _href
        upload_name = upload_request['_href'].replace('/pulp/api/v3/uploads/', '')[:-1]

        self.addCleanup(self.client.delete, upload_request['_href'])
        cmd = ('ls', os.path.join(MEDIA_PATH, 'upload', upload_name))
        self.cli_client.run(cmd, sudo=True)

        # delete
        self.doCleanups()
        with self.assertRaises(CalledProcessError):
            self.cli_client.run(cmd, sudo=True)

    def upload_chunks(self):
        header_first_chunk = {
            'Content-Range': 'bytes 0-{}/{}'.format(
                len(self.first_chunk) - 1, self.size_file
            )
        }

        header_second_chunk = {
            'Content-Range': 'bytes {}-{}/{}'.format(
                len(self.first_chunk), self.size_file - 1, self.size_file
            )
        }

        chunked_data = [
            [self.first_chunk, header_first_chunk],
            [self.second_chunk, header_second_chunk],
        ]
        shuffle(chunked_data)

        upload_request = self.client.post(
            UPLOAD_PATH, {'size': self.size_file}
        )

        for data in chunked_data:
            self.client.put(
                upload_request['_href'],
                files={'file': data[0]},
                headers=data[1],
            )

        self.client.put(
            urljoin(upload_request['_href'], 'commit/'),
            data={'sha256': self.file_sha256},
        )

        return upload_request
