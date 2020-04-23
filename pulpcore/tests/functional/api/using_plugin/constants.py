# coding=utf-8
"""Constants for pulpcore API tests that require the use of a plugin."""
from urllib.parse import urljoin

from pulp_smash import config
from pulp_smash.pulp3.constants import (
    BASE_DISTRIBUTION_PATH,
    BASE_PUBLICATION_PATH,
    BASE_REMOTE_PATH,
    BASE_REPO_PATH,
    BASE_CONTENT_PATH,
)

PULP_FIXTURES_BASE_URL = config.get_config().get_fixtures_url()

FILE_CONTENT_NAME = "file.file"

FILE_CONTENT_PATH = urljoin(BASE_CONTENT_PATH, "file/files/")

FILE_REMOTE_PATH = urljoin(BASE_REMOTE_PATH, "file/file/")

FILE_REPO_PATH = urljoin(BASE_REPO_PATH, "file/file/")

FILE_DISTRIBUTION_PATH = urljoin(BASE_DISTRIBUTION_PATH, "file/file/")

FILE_PUBLICATION_PATH = urljoin(BASE_PUBLICATION_PATH, "file/file/")

FILE_CHUNKED_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "file-chunked/")

FILE_TO_BE_CHUNKED_URL = urljoin(FILE_CHUNKED_FIXTURE_URL, "1.iso")

FILE_CHUNKED_MANIFEST_URL = urljoin(FILE_CHUNKED_FIXTURE_URL, "PULP_MANIFEST")

FILE_CHUNKED_PART_1_URL = urljoin(FILE_CHUNKED_FIXTURE_URL, "chunkaa")

FILE_CHUNKED_PART_2_URL = urljoin(FILE_CHUNKED_FIXTURE_URL, "chunkab")

FILE_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "file/")
"""The URL to a file repository."""

FILE_FIXTURE_MANIFEST_URL = urljoin(FILE_FIXTURE_URL, "PULP_MANIFEST")
"""The URL to a file repository manifest."""

FILE_FIXTURE_COUNT = 3
"""The number of packages available at :data:`FILE_FIXTURE_URL`."""

FILE_FIXTURE_SUMMARY = {FILE_CONTENT_NAME: FILE_FIXTURE_COUNT}
"""The desired content summary after syncing :data:`FILE_FIXTURE_URL`."""

FILE2_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "file2/")
"""The URL to a file repository."""

FILE2_FIXTURE_MANIFEST_URL = urljoin(FILE2_FIXTURE_URL, "PULP_MANIFEST")
"""The URL to a file repository manifest"""

FILE_MANY_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "file-many/")
"""The URL to a file repository containing many files."""

FILE_MANY_FIXTURE_MANIFEST_URL = urljoin(FILE_MANY_FIXTURE_URL, "PULP_MANIFEST")
"""The URL to a file repository manifest"""

FILE_MANY_FIXTURE_COUNT = 250
"""The number of packages available at :data:`FILE_MANY_FIXTURE_URL`."""

FILE_LARGE_FIXTURE_URL = urljoin(PULP_FIXTURES_BASE_URL, "file-large/")
"""The URL to a file repository containing a large number of files."""

FILE_LARGE_URL = urljoin(FILE_LARGE_FIXTURE_URL, "1.iso")
"""The URL to a large ISO file at :data:`FILE_LARGE_FIXTURE_URL`."""

FILE_LARGE_FIXTURE_COUNT = 10
"""The number of packages available at :data:`FILE_LARGE_FIXTURE_URL`."""

FILE_LARGE_FIXTURE_MANIFEST_URL = urljoin(FILE_LARGE_FIXTURE_URL, "PULP_MANIFEST")
"""The URL to a file repository manifest."""

FILE_URL = urljoin(FILE_FIXTURE_URL, "1.iso")
"""The URL to an ISO file at :data:`FILE_FIXTURE_URL`."""

FILE2_URL = urljoin(FILE2_FIXTURE_URL, "1.iso")
"""The URL to an ISO file at :data:`FILE2_FIXTURE_URL`."""
