# coding=utf-8
"""Tests related to content upload."""
import hashlib
import unittest
from random import shuffle
from urllib.parse import urljoin

from pulp_smash import api, config
from pulp_smash.utils import http_get
from pulp_smash.pulp3.constants import ARTIFACTS_PATH, UPLOAD_PATH

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

    This test targets the following issue:

    * `Pulp #4197 <https://pulp.plan.io/issues/4197>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        cls.file = http_get(FILE_TO_BE_CHUNKED_URL)
        cls.file_sha256 = hashlib.sha256(cls.file).hexdigest()
        cls.size_file = len(cls.file)

    def test_create_artifact(self):
        """Test creation of artifact using upload of files in chunks."""
        first_chunk = http_get(FILE_CHUNKED_PART_1_URL)
        header_first_chunk = {
            'Content-Range': 'bytes 0-{}/{}'.format(
                len(first_chunk) - 1, self.size_file
            )
        }

        second_chunk = http_get(FILE_CHUNKED_PART_2_URL)
        header_second_chunk = {
            'Content-Range': 'bytes {}-{}/{}'.format(
                len(first_chunk), self.size_file - 1, self.size_file
            )
        }

        chunked_data = [
            [first_chunk, header_first_chunk],
            [second_chunk, header_second_chunk],
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

        response = self.client.post(
            ARTIFACTS_PATH, {'upload': upload_request['_href']}
        )

        artifact = self.client.get(response['_href'])
        self.addCleanup(self.client.delete, artifact['_href'])

        self.assertEqual(artifact['sha256'], self.file_sha256, artifact)
