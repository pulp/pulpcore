"""Tests for If-Modified-Since / 304 Not Modified on the content app.

When a client already has a copy of a file it can send an If-Modified-Since header
asking the content app to reply "304 Not Modified" (an empty body) instead of
re-sending the whole file. These tests cover that conversation.
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
from pulpcore.content.handler import EDGE_CACHE_CONTROL


def assert_full_download(response):
    """The server sent the whole file, plus the headers a client reuses to revalidate later."""
    assert response.status_code == 200
    assert response.content
    assert response.headers.get("Cache-Control") == EDGE_CACHE_CONTROL
    # Last-Modified must be a real date in the past - never missing, epoch, or in the future.
    last_modified = response.headers.get("Last-Modified")
    assert last_modified
    assert 0 < parse_http_date(last_modified) <= time.time()


def assert_not_modified(response):
    """The server skipped the download: a 304 with an empty body but the caching header intact."""
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers.get("Cache-Control") == EDGE_CACHE_CONTROL


def assert_object_storage_redirect(response):
    """On Azure/S3, pulpcore answers with a 302 to the object store, carrying the revalidation
    headers - it does not stream the bytes itself."""
    assert response.status_code == 302
    assert response.headers.get("Location")
    assert response.headers.get("Cache-Control") == EDGE_CACHE_CONTROL
    # Last-Modified must be a real date in the past - never missing, epoch, or in the future.
    last_modified = response.headers.get("Last-Modified")
    assert last_modified
    assert 0 < parse_http_date(last_modified) <= time.time()


@pytest.fixture
def assert_full_response(pulp_settings):
    """Return the right assertion for a served (non-304) response on this backend: full bytes on
    the filesystem, or a redirect to the object store on Azure/S3."""
    backend = pulp_settings.STORAGES["default"]["BACKEND"]
    redirects = (
        backend != "pulpcore.app.models.storage.FileSystem"
        and pulp_settings.REDIRECT_TO_OBJECT_STORAGE
    )
    return assert_object_storage_redirect if redirects else assert_full_download


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
def test_a_current_copy_is_not_redownloaded(distribution_url, assert_full_response):
    """A client whose copy is already up to date gets a 304 instead of the file."""
    url = urljoin(distribution_url, "1.iso")

    # Download once and remember the date the server reported.
    first = requests.get(url, allow_redirects=False)
    assert_full_response(first)
    served_date = first.headers["Last-Modified"]

    # Asking again with that exact date -> nothing changed -> 304.
    reused = requests.get(url, headers={"If-Modified-Since": served_date}, allow_redirects=False)
    assert_not_modified(reused)

    # A client claiming an even newer copy than the server's is also told 304.
    tomorrow = http_date(time.time() + 3600)
    newer = requests.get(url, headers={"If-Modified-Since": tomorrow}, allow_redirects=False)
    assert_not_modified(newer)


@pytest.mark.parallel
def test_a_stale_copy_gets_the_full_file(distribution_url, assert_full_response):
    """A client whose copy predates the file downloads the whole thing again."""
    url = urljoin(distribution_url, "1.iso")

    # "I last saw this at the dawn of time" -> the file is newer -> send it all.
    long_ago = http_date(0)
    response = requests.get(url, headers={"If-Modified-Since": long_ago}, allow_redirects=False)
    assert_full_response(response)


@pytest.mark.parallel
def test_authorization_runs_before_revalidation(
    distribution,
    distribution_url,
    assert_full_response,
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    monitor_task,
):
    """A content guard is checked on every request - even one that would answer 304."""
    url = urljoin(distribution_url, "1.iso")

    # Protect the distribution: callers must send x-header: base64("123456").
    guard = gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsHeaderApi,
        {"name": str(uuid4()), "header_name": "x-header", "header_value": "123456"},
    )
    body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
    monitor_task(
        file_bindings.DistributionsFileApi.partial_update(distribution.pulp_href, body).task
    )

    credentials = {"x-header": b64encode(b"123456").decode("ascii")}
    tomorrow = http_date(time.time() + 3600)

    # No credentials -> rejected up front, before any 304 revalidation can happen.
    denied = requests.get(url, headers={"If-Modified-Since": tomorrow}, allow_redirects=False)
    assert denied.status_code == 403

    # With credentials the normal conversation works: full download, then 304.
    authorized = requests.get(url, headers=credentials, allow_redirects=False)
    assert_full_response(authorized)

    revalidated = requests.get(
        url,
        headers={**credentials, "If-Modified-Since": tomorrow},
        allow_redirects=False,
    )
    assert_not_modified(revalidated)


@pytest.mark.parallel
def test_cache_still_honors_conditional_requests(
    distribution_url, assert_full_response, redis_status
):
    """A cached response revalidates to 304 but still serves the file to a client without a copy."""
    if not redis_status:
        pytest.skip("Could not connect to the Redis server")

    url = urljoin(distribution_url, "1.iso")

    # Warm the cache with a normal download.
    assert_full_response(requests.get(url, allow_redirects=False))

    # A cached response can still answer a conditional request with a 304.
    tomorrow = http_date(time.time() + 3600)
    revalidated = requests.get(url, headers={"If-Modified-Since": tomorrow}, allow_redirects=False)
    assert_not_modified(revalidated)
    assert revalidated.headers.get("X-PULP-CACHE") == "HIT"

    # A client without a copy still gets the full file from that same cache entry.
    fresh = requests.get(url, allow_redirects=False)
    assert_full_response(fresh)
    assert fresh.headers.get("X-PULP-CACHE") == "HIT"
