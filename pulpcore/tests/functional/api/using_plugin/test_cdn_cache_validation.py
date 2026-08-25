"""Tests for content cache validation and object-storage redirects.

When a client already has a copy of a file it can send an If-Modified-Since or If-None-Match header
asking the content app to reply "304 Not Modified" (an empty body) instead of re-sending the file.
Object-storage redirects include Cache-Control: no-store.
"""

import time
from base64 import b64encode
from urllib.parse import urljoin
from uuid import uuid4

import pytest
import requests
from django.utils.http import http_date, parse_http_date

from pulpcore.client.pulp_file import (
    FileRepositorySyncURL,
    PatchedfileFileDistribution,
)
from pulpcore.content.handler import EDGE_CACHE_CONTROL, NO_STORE_EDGE_CACHE_CONTROL


def assert_full_download(response):
    """The server sent the whole file, plus the headers a client reuses to revalidate later."""
    assert response.status_code == 200
    assert response.content
    assert response.headers.get("Cache-Control") == EDGE_CACHE_CONTROL
    # Last-Modified must be a real date in the past - never missing, epoch, or in the future
    last_modified = response.headers.get("Last-Modified")
    assert last_modified
    assert 0 < parse_http_date(last_modified) <= time.time()


def assert_not_modified(response):
    """The server skipped the download: a 304 with an empty body."""
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers.get("Cache-Control") == EDGE_CACHE_CONTROL


def tomorrow():
    return http_date(time.time() + 24 * 60 * 60)


def dawn_of_time():
    return http_date(0)


@pytest.fixture
def distribution(
    file_repo_with_auto_publish,
    file_remote_factory,
    file_bindings,
    file_distribution_factory,
    monitor_task,
    basic_manifest_path,
):
    """Sync a small file repo, auto-publish it, and distribute it. Returns the distribution."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    return file_distribution_factory(repository=repo.pulp_href)


@pytest.fixture
def distribution_url(distribution, distribution_base_url):
    """The externally reachable base URL where `distribution` serves its files."""
    return distribution_base_url(distribution.base_url)


@pytest.mark.parallel
class TestFileSystemStorage:
    @pytest.fixture(autouse=True)
    def require_filesystem_storage(self, pulp_settings):
        if pulp_settings.STORAGES["default"]["BACKEND"] != "pulpcore.app.models.storage.FileSystem":
            pytest.skip("Requires filesystem storage")

    def test_a_current_copy_is_not_redownloaded(self, distribution_url):
        """A client whose copy is up to date gets a 304 instead of the file."""
        url = urljoin(distribution_url, "1.iso")

        # Download once and remember the date the server reported
        first = requests.get(url, allow_redirects=False)
        assert_full_download(first)
        served_date = first.headers["Last-Modified"]

        # Asking again with that exact date -> nothing changed -> 304
        reused = requests.get(
            url, headers={"If-Modified-Since": served_date}, allow_redirects=False
        )
        assert_not_modified(reused)

        # A client claiming an even newer copy than the server's is also told 304
        newer = requests.get(url, headers={"If-Modified-Since": tomorrow()}, allow_redirects=False)
        assert_not_modified(newer)

        # CDN cached Last-Modified is old -> the file is newer -> send it all
        response = requests.get(
            url, headers={"If-Modified-Since": dawn_of_time()}, allow_redirects=False
        )
        assert_full_download(response)

    def test_authorization_runs_before_revalidation(
        self,
        distribution,
        distribution_url,
        pulpcore_bindings,
        file_bindings,
        gen_object_with_cleanup,
        monitor_task,
        redis_status,
    ):
        """A content guard is checked before revalidation, with or without Redis."""
        url = urljoin(distribution_url, "1.iso")

        # Protect the distribution: callers must send x-header: base64("123456")
        guard = gen_object_with_cleanup(
            pulpcore_bindings.ContentguardsHeaderApi,
            {"name": str(uuid4()), "header_name": "x-header", "header_value": "123456"},
        )
        body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
        monitor_task(
            file_bindings.DistributionsFileApi.partial_update(distribution.pulp_href, body).task
        )
        credentials = {"x-header": b64encode(b"123456").decode("ascii")}

        # Populate Redis, when available, before the unauthorized request
        authorized = requests.get(url, headers=credentials, allow_redirects=False)
        assert_full_download(authorized)

        # No credentials -> rejected before 304 revalidation can happen
        denied = requests.get(url, headers={"If-Modified-Since": tomorrow()}, allow_redirects=False)
        assert denied.status_code == 403
        assert denied.headers.get("X-PULP-CACHE") is None

        revalidated = requests.get(
            url,
            headers={**credentials, "If-Modified-Since": tomorrow()},
            allow_redirects=False,
        )
        assert_not_modified(revalidated)
        if redis_status:
            assert authorized.headers.get("X-PULP-CACHE") == "MISS"
            assert revalidated.headers.get("X-PULP-CACHE") == "HIT"

    def test_cache_still_honors_conditional_requests(self, distribution_url, redis_status):
        """A Redis hit can return 304 and still serve an unconditional request."""
        if not redis_status:
            pytest.skip("Could not connect to the Redis server")

        url = urljoin(distribution_url, "1.iso")
        # Warm the cache with a normal download
        assert_full_download(requests.get(url, allow_redirects=False))

        # A cached response can still answer a conditional request with a 304
        revalidated = requests.get(
            url, headers={"If-Modified-Since": tomorrow()}, allow_redirects=False
        )
        assert_not_modified(revalidated)
        assert revalidated.headers.get("X-PULP-CACHE") == "HIT"

        # A client without a copy still gets the full file from that same cache entry
        fresh = requests.get(url, allow_redirects=False)
        assert_full_download(fresh)
        assert fresh.headers.get("X-PULP-CACHE") == "HIT"

    def test_etag_revalidation(
        self,
        distribution_url,
        file_repo_with_auto_publish,
        write_3_iso_file_fixture_data_factory,
        file_remote_factory,
        file_bindings,
        monitor_task,
    ):
        """An ETag validates unchanged content but not changed content at the same URL."""
        # A fresh request returns a response with the etag
        url = urljoin(distribution_url, "1.iso")
        first = requests.get(url, allow_redirects=False)
        assert_full_download(first)
        old_etag = first.headers["ETag"]

        # The etag is a match
        reused = requests.get(url, headers={"If-None-Match": old_etag}, allow_redirects=False)
        assert_not_modified(reused)
        assert reused.headers["ETag"] == old_etag

        # Replace file in repo, so it's available through the same url (but modified)
        manifest = write_3_iso_file_fixture_data_factory("updated")
        remote = file_remote_factory(manifest_path=manifest, policy="immediate")
        body = FileRepositorySyncURL(remote=remote.pulp_href)
        monitor_task(
            file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
        )

        # The etag is no longer a match
        changed = requests.get(url, headers={"If-None-Match": old_etag}, allow_redirects=False)
        assert_full_download(changed)
        assert changed.content != first.content
        assert changed.headers["ETag"] != old_etag


@pytest.mark.parallel
class TestObjectStorageRedirect:
    @pytest.fixture(autouse=True)
    def require_object_storage_redirect(self, pulp_settings):
        backend = pulp_settings.STORAGES["default"]["BACKEND"]
        if (
            backend == "pulpcore.app.models.storage.FileSystem"
            or not pulp_settings.REDIRECT_TO_OBJECT_STORAGE
        ):
            pytest.skip("Requires object-storage redirects")

    def test_cold_request_without_if_modified_since(self, distribution_url):
        """A signed redirect can be revalidated with Last-Modified."""
        url = urljoin(distribution_url, "1.iso")

        # The first redirect supplies the Last-Modified date for revalidation
        first = requests.get(url, allow_redirects=False)
        assert first.status_code == 302
        assert first.headers.get("Location")
        assert first.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL
        last_modified = first.headers["Last-Modified"]

        # Regardless if CDN respected Cache-Control, Pulp follow the protocol
        reused_date = requests.get(
            url, headers={"If-Modified-Since": last_modified}, allow_redirects=False
        )
        assert reused_date.status_code == 304
        assert first.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL

        # Regardless if CDN respected Cache-Control, Pulp follow the protocol
        stale_date = requests.get(
            url, headers={"If-Modified-Since": dawn_of_time()}, allow_redirects=False
        )
        assert stale_date.status_code == 302
        assert stale_date.headers.get("Location")
        assert stale_date.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL

    def test_cold_request_with_if_modified_since(self, distribution_url, redis_status):
        """A signed redirect can be revalidated with Last-Modified."""
        url = urljoin(distribution_url, "1.iso")

        # A future modification date returns 304
        first = requests.get(url, allow_redirects=False, headers={"If-Modified-Since": tomorrow()})
        assert first.status_code == 304
        assert first.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL

        # A stale date returns the redirect; Redis serves the cached redirect when available
        second = requests.get(
            url, headers={"If-Modified-Since": dawn_of_time()}, allow_redirects=False
        )
        assert second.status_code == 302
        assert second.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL
        if redis_status:
            assert second.headers.get("X-PULP-CACHE") == "HIT"

        # A future date returns 304; Redis serves the cached response when available
        third = requests.get(url, headers={"If-Modified-Since": tomorrow()}, allow_redirects=False)
        assert third.status_code == 304
        assert third.headers.get("Cache-Control") == NO_STORE_EDGE_CACHE_CONTROL
        if redis_status:
            assert third.headers.get("X-PULP-CACHE") == "HIT"
