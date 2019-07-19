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
    * `Pulp #4982 <https://pulp.plan.io/issues/4982>`_
    * `Pulp #5150 <https://pulp.plan.io/issues/5150>`_
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

        first_chunk = http_get(FILE_CHUNKED_PART_1_URL)
        header_first_chunk = {
            'Content-Range': 'bytes 0-{}/{}'.format(
                len(first_chunk) - 1, cls.size_file
            )
        }

        second_chunk = http_get(FILE_CHUNKED_PART_2_URL)
        header_second_chunk = {
            'Content-Range': 'bytes {}-{}/{}'.format(
                len(first_chunk), cls.size_file - 1, cls.size_file
            )
        }

        cls.chunked_data = [
            [first_chunk, header_first_chunk],
            [second_chunk, header_second_chunk],
        ]
        shuffle(cls.chunked_data)

    def test_create_artifact_without_checksum(self):
        """Test creation of artifact using upload of files in chunks."""

        upload_request = self.upload_chunks()

        response = self.client.post(
            ARTIFACTS_PATH, {'upload': upload_request['_href']}
        )

        artifact = self.client.get(response['_href'])
        self.addCleanup(self.client.delete, artifact['_href'])

        self.assertEqual(artifact['sha256'], self.file_sha256, artifact)

    def test_create_artifact_passing_checksum(self):
        """Test creation of artifact using upload of files in chunks passing checksum."""
        upload_request = self.client.post(
            UPLOAD_PATH, {'size': self.size_file}
        )

        for data in self.chunked_data:
            self.client.put(
                upload_request['_href'],
                data={'sha256': hashlib.sha256(data[0]).hexdigest()},
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

    def test_upload_chunk_wrong_checksum(self):
        """Test creation of artifact using upload of files in chunks passing wrong checksum."""
        self.client.response_handler = api.echo_handler

        upload_request = self.client.post(
            UPLOAD_PATH, {'size': self.size_file}
        )

        for data in self.chunked_data:
            response = self.client.put(
                upload_request.json()['_href'],
                data={'sha256': "WRONG CHECKSUM"},
                files={'file': data[0]},
                headers=data[1],
            )

            assert response.status_code == 400

    def test_upload_response(self):
        """Test upload responses when creating an upload and uploading chunks."""
        self.client.response_handler = api.echo_handler

        upload_request = self.client.post(
            UPLOAD_PATH, {'size': self.size_file}
        )

        expected_keys = ['_href', '_created', 'size', 'completed']

        self.assertEquals([*upload_request.json()], expected_keys)

        for data in self.chunked_data:
            response = self.client.put(
                upload_request.json()['_href'],
                files={'file': data[0]},
                headers=data[1],
            )

            self.assertEquals([*response.json()], expected_keys)

        response = self.client.get(upload_request.json()['_href'])

        expected_keys = ['_href', '_created', 'size', 'completed', 'chunks']

        self.assertEquals([*response.json()], expected_keys)

        expected_chunks = [
            {'offset': 0, 'size': 6291456},
            {'offset': 6291456, 'size': 4194304}
        ]

        sorted_chunks_response = sorted(response.json()['chunks'], key=lambda i: i['offset'])
        self.assertEquals(sorted_chunks_response, expected_chunks)

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
        upload_request = self.client.post(
            UPLOAD_PATH, {'size': self.size_file}
        )

        for data in self.chunked_data:
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
