import pytest

from pulpcore.app.models import Artifact
from pulpcore.download import BaseDownloader
from pulpcore.plugin.exceptions import UnsupportedDigestValidationError


@pytest.fixture(autouse=True)
def _patch_digest_fields(monkeypatch):
    monkeypatch.setattr(Artifact, "DIGEST_FIELDS", {"sha512", "sha256"})


def test_no_trusted_digest():
    url = "http://example.com"
    with pytest.raises(UnsupportedDigestValidationError):
        BaseDownloader(
            url,
            expected_digests={"sha1": "912ec803b2ce49e4a541068d495ab570"},
            expected_size=None,
            semaphore=None,
        )


def test_no_expected_digests():
    url = "http://example.com"
    downloader = BaseDownloader(
        url,
        expected_digests=None,
        expected_size=None,
        semaphore=None,
    )
    assert downloader.expected_digests is None


def test_expected_digests():
    url = "http://example.com"
    digests = {
        "sha1": "912ec803b2ce49e4a541068d495ab570",
        "sha256": "b361886f33f1b6089626dc8bd80961356f9a2911091ecb2ffa33730beb83bbdb",
    }
    downloader = BaseDownloader(
        url,
        expected_digests=digests,
        expected_size=None,
        semaphore=None,
    )
    assert downloader.expected_digests == digests
