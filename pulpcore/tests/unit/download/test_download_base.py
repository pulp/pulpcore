from unittest import mock

from django.test import TestCase

from pulpcore.download import BaseDownloader
from pulpcore.plugin.exceptions import UnsupportedDigestValidationError


class BaseDownloaderInitTestCase(TestCase):
    @mock.patch(
        "pulpcore.app.models.Artifact.DIGEST_FIELDS",
        new_callable=mock.PropertyMock,
        return_value=set(["sha512", "sha256"]),
    )
    def test_no_trusted_digest(self, mock_DIGEST_FIELDS):
        url = "http://example.com"
        with self.assertRaises(UnsupportedDigestValidationError):
            BaseDownloader(
                url,
                custom_file_object=None,
                expected_digests={"sha1": "912ec803b2ce49e4a541068d495ab570"},
                expected_size=None,
                semaphore=None,
            )

    @mock.patch(
        "pulpcore.app.models.Artifact.DIGEST_FIELDS",
        new_callable=mock.PropertyMock,
        return_value=set(["sha512", "sha256"]),
    )
    def test_no_expected_digests(self, mock_DIGEST_FIELDS):
        url = "http://example.com"
        downloader = BaseDownloader(
            url,
            custom_file_object=None,
            expected_digests=None,
            expected_size=None,
            semaphore=None,
        )
        assert downloader.expected_digests is None

    @mock.patch(
        "pulpcore.app.models.Artifact.DIGEST_FIELDS",
        new_callable=mock.PropertyMock,
        return_value=set(["sha512", "sha256"]),
    )
    def test_expected_digests(self, mock_DIGEST_FIELDS):
        url = "http://example.com"
        digests = {
            "sha1": "912ec803b2ce49e4a541068d495ab570",
            "sha256": "b361886f33f1b6089626dc8bd80961356f9a2911091ecb2ffa33730beb83bbdb",
        }
        downloader = BaseDownloader(
            url,
            custom_file_object=None,
            expected_digests=digests,
            expected_size=None,
            semaphore=None,
        )
        assert downloader.expected_digests == digests
