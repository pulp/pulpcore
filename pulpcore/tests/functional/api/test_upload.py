"""Tests related to content upload."""
import hashlib
import unittest

from random import shuffle
from requests import HTTPError
from urllib.parse import urljoin

from pulp_smash import api, cli, config
from pulp_smash.pulp3.constants import UPLOAD_PATH
from pulp_smash.utils import http_get

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
    * `Pulp #4982 <https://pulp.plan.io/issues/4982>`_
    * `Pulp #5092 <https://pulp.plan.io/issues/5092>`_
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
            "Content-Range": "bytes 0-{}/{}".format(len(first_chunk) - 1, cls.size_file)
        }

        second_chunk = http_get(FILE_CHUNKED_PART_2_URL)
        header_second_chunk = {
            "Content-Range": "bytes {}-{}/{}".format(
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

        _, artifact = self.upload_chunks()

        self.addCleanup(self.client.delete, artifact["pulp_href"])

        self.assertEqual(artifact["sha256"], self.file_sha256, artifact)

    def test_create_artifact_passing_checksum(self):
        """Test creation of artifact using upload of files in chunks passing checksum."""
        upload_request = self.client.post(UPLOAD_PATH, {"size": self.size_file})

        for data in self.chunked_data:
            self.client.put(
                upload_request["pulp_href"],
                data={"sha256": hashlib.sha256(data[0]).hexdigest()},
                files={"file": data[0]},
                headers=data[1],
            )

        artifact_request = self.client.post(
            urljoin(upload_request["pulp_href"], "commit/"), data={"sha256": self.file_sha256}
        )

        self.addCleanup(self.client.delete, artifact_request["pulp_href"])

        self.assertEqual(artifact_request["sha256"], self.file_sha256, artifact_request)

    def test_upload_chunk_wrong_checksum(self):
        """Test creation of artifact using upload of files in chunks passing wrong checksum."""
        upload_request = self.client.post(UPLOAD_PATH, {"size": self.size_file})

        for data in self.chunked_data:
            response = self.client.using_handler(api.echo_handler).put(
                upload_request["pulp_href"],
                data={"sha256": "WRONG CHECKSUM"},
                files={"file": data[0]},
                headers=data[1],
            )
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 400, response)

        self.addCleanup(self.client.delete, upload_request["pulp_href"])

    def test_upload_response(self):
        """Test upload responses when creating an upload and uploading chunks."""
        upload_request = self.client.post(UPLOAD_PATH, {"size": self.size_file})

        expected_keys = ["pulp_href", "pulp_created", "size"]

        self.assertEqual([*upload_request], expected_keys, upload_request)

        for data in self.chunked_data:
            response = self.client.put(
                upload_request["pulp_href"], files={"file": data[0]}, headers=data[1]
            )

            with self.subTest(response=response):
                self.assertEqual([*response], expected_keys, response)

        response = self.client.get(upload_request["pulp_href"])

        expected_keys.append("chunks")

        self.assertEqual([*response], expected_keys, response)

        expected_chunks = [
            {"offset": 0, "size": 6291456},
            {"offset": 6291456, "size": 4194304},
        ]

        sorted_chunks_response = sorted(response["chunks"], key=lambda i: i["offset"])
        self.assertEqual(sorted_chunks_response, expected_chunks, response)
        self.addCleanup(self.client.delete, response["pulp_href"])

    def test_delete_upload(self):
        """Check whether uploads are being correctly deleted after committing."""
        upload, artifact = self.upload_chunks()

        with self.assertRaises(HTTPError):
            self.client.get(upload["pulp_href"])

        self.addCleanup(self.client.delete, artifact["pulp_href"])

    def upload_chunks(self):
        """Upload file in chunks."""
        upload_request = self.client.post(UPLOAD_PATH, {"size": self.size_file})

        for data in self.chunked_data:
            self.client.put(upload_request["pulp_href"], files={"file": data[0]}, headers=data[1])

        artifact_request = self.client.post(
            urljoin(upload_request["pulp_href"], "commit/"), data={"sha256": self.file_sha256}
        )
        return upload_request, artifact_request
