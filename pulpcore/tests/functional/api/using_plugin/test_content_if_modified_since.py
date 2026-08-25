"""Tests for If-Modified-Since / 304 Not Modified on the content app."""

from base64 import b64encode
from time import sleep, time
from urllib.parse import urljoin
from uuid import uuid4

import pytest
import requests
from django.utils.http import http_date, parse_http_date

from pulpcore.client.pulp_file import FileRepositorySyncURL, PatchedfileFileDistribution
from pulpcore.content.handler import Handler

CACHE_CONTROL = Handler.response_headers("1.iso")["Cache-Control"]
ONE_DAY_SECONDS = 86400


def _get(url, headers=None):
    """GET the content-app response without following object-storage redirects."""
    return requests.get(url, headers=headers, allow_redirects=False)


def _assert_artifact_200(response):
    assert response.status_code == 200
    assert response.content
    assert response.headers.get("Cache-Control") == CACHE_CONTROL
    assert response.headers.get("Last-Modified")


def _get_and_assert_last_modified(url, headers=None):
    """GET the artifact, assert a full 200, and return (response, Last-Modified value)."""
    response = _get(url, headers=headers)
    _assert_artifact_200(response)
    return response, response.headers["Last-Modified"]


def _assert_304(response, last_modified):
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers.get("Last-Modified") == last_modified
    assert response.headers.get("Cache-Control") == CACHE_CONTROL


@pytest.fixture
def redis_required(redis_status):
    """Skip when the content cache (Redis) is not reachable."""
    if not redis_status:
        pytest.skip("Could not connect to the Redis server")


@pytest.fixture
def inline_storage(pulp_settings):
    """Skip when the instance redirects to object storage instead of serving bytes inline.

    The 304 path applies to filesystem/ArtifactResponse serving; object-storage 302s are not
    304'd by design.
    """
    backend = pulp_settings.STORAGES["default"]["BACKEND"]
    redirects = (
        backend != "pulpcore.app.models.storage.FileSystem"
        and pulp_settings.REDIRECT_TO_OBJECT_STORAGE
    )
    if redirects:
        pytest.skip("object-storage redirects are not 304'd by design")


@pytest.fixture
def object_storage_redirects(pulp_settings):
    """Skip unless the instance redirects to object storage (302)."""
    backend = pulp_settings.STORAGES["default"]["BACKEND"]
    if (
        backend == "pulpcore.app.models.storage.FileSystem"
        or not pulp_settings.REDIRECT_TO_OBJECT_STORAGE
    ):
        pytest.skip("not using object-storage redirects")


@pytest.fixture
def published_file_distribution(
    file_repo_with_auto_publish,
    file_remote_factory,
    file_bindings,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
    basic_manifest_path,
):
    """Immediate-sync a 3-file repo, distribute it, and return (repo, distro, base_url)."""
    remote = file_remote_factory(manifest_path=basic_manifest_path, policy="immediate")
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    distro = file_distribution_factory(repository=repo.pulp_href)
    return repo, distro, distribution_base_url(distro.base_url)


@pytest.mark.parallel
def test_artifact_get_sets_last_modified_and_cache_control(
    published_file_distribution, inline_storage, redis_status
):
    """A plain 200 carries the Last-Modified validator and revalidate Cache-Control."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    response = _get(url)
    _assert_artifact_200(response)
    last_modified = response.headers["Last-Modified"]

    if redis_status:
        assert response.headers.get("X-PULP-CACHE") == "MISS"
        cached = _get(url)
        _assert_artifact_200(cached)
        assert cached.headers.get("X-PULP-CACHE") == "HIT"
        assert cached.headers["Last-Modified"] == last_modified


@pytest.mark.parallel
def test_matching_if_modified_since_returns_304(
    published_file_distribution, inline_storage, redis_status
):
    """An If-Modified-Since at or after the validator gets a bodyless 304."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    _first, last_modified = _get_and_assert_last_modified(url)

    matched = _get(url, headers={"If-Modified-Since": last_modified})
    _assert_304(matched, last_modified)

    sleep(2)
    later_response = _get(url, headers={"If-Modified-Since": http_date()})
    _assert_304(later_response, last_modified)

    if redis_status:
        assert matched.headers.get("X-PULP-CACHE") == "HIT"
        warm = _get(url)
        _assert_artifact_200(warm)
        assert warm.headers.get("X-PULP-CACHE") == "HIT"
        assert warm.content


@pytest.mark.parallel
def test_stale_garbage_and_future_if_modified_since_return_200(
    published_file_distribution, inline_storage
):
    """Older, unparseable, or future If-Modified-Since values fall back to a full 200."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    _first, last_modified = _get_and_assert_last_modified(url)
    last_modified_epoch = parse_http_date(last_modified)

    stale = http_date(last_modified_epoch - ONE_DAY_SECONDS)
    future = http_date(time() + ONE_DAY_SECONDS)
    for if_modified_since in (stale, "not a date", future):
        response = _get(url, headers={"If-Modified-Since": if_modified_since})
        _assert_artifact_200(response)
        assert response.headers["Last-Modified"] == last_modified


@pytest.mark.parallel
def test_last_modified_is_membership_not_version_time(
    file_bindings,
    file_repository_factory,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
    inline_storage,
):
    """Last-Modified is the served unit's membership time, not the repo version's time."""
    repo = file_repository_factory(autopublish=True)
    content_a = file_content_unit_with_name_factory(f"{uuid4()}.iso")
    content_b = file_content_unit_with_name_factory(f"{uuid4()}.iso")

    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content_a.pulp_href]}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    version_1 = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)

    sleep(2)

    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href, {"add_content_units": [content_b.pulp_href]}
        ).task
    )
    repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)
    version_2 = file_bindings.RepositoriesFileVersionsApi.read(repo.latest_version_href)

    distro = file_distribution_factory(repository=repo.pulp_href)
    url = urljoin(distribution_base_url(distro.base_url), content_a.relative_path)
    response = _get(url)
    _assert_artifact_200(response)

    last_modified = parse_http_date(response.headers["Last-Modified"])
    v1_created = version_1.pulp_created.timestamp()
    v2_created = version_2.pulp_created.timestamp()

    # content_a joined the repo in version 1, so its validator predates version 2 entirely...
    assert last_modified < v2_created
    # ...and sits at version 1's creation (within HTTP-date's 1-second resolution), not later.
    assert last_modified <= v1_created + 1


@pytest.mark.parallel
def test_last_modified_is_membership_not_content_created(
    file_bindings,
    file_repository_factory,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
    inline_storage,
):
    """One unit in two repos yields per-repo validators, not the unit's created time."""
    content = file_content_unit_with_name_factory(f"{uuid4()}.iso")
    repo_a = file_repository_factory(autopublish=True)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo_a.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
    )
    distro_a = file_distribution_factory(repository=repo_a.pulp_href)
    url_a = urljoin(distribution_base_url(distro_a.base_url), content.relative_path)
    response_a = _get(url_a)
    _assert_artifact_200(response_a)

    sleep(2)

    repo_b = file_repository_factory(autopublish=True)
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo_b.pulp_href, {"add_content_units": [content.pulp_href]}
        ).task
    )
    distro_b = file_distribution_factory(repository=repo_b.pulp_href)
    url_b = urljoin(distribution_base_url(distro_b.base_url), content.relative_path)
    response_b = _get(url_b)
    _assert_artifact_200(response_b)

    last_modified_a = parse_http_date(response_a.headers["Last-Modified"])
    last_modified_b = parse_http_date(response_b.headers["Last-Modified"])
    content_created = content.pulp_created.timestamp()

    assert last_modified_b > last_modified_a
    assert last_modified_b > content_created


@pytest.mark.parallel
def test_content_guard_still_runs_before_304(
    published_file_distribution,
    inline_storage,
    pulpcore_bindings,
    file_bindings,
    gen_object_with_cleanup,
    monitor_task,
):
    """Authorization runs on every request: a conditional GET is 403'd before any 304."""
    _repo, distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")
    guard = gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsHeaderApi,
        {
            "name": str(uuid4()),
            "header_name": "x-header",
            "header_value": "123456",
        },
    )
    body = PatchedfileFileDistribution(content_guard=guard.pulp_href)
    monitor_task(file_bindings.DistributionsFileApi.partial_update(distro.pulp_href, body).task)

    auth_headers = {"x-header": b64encode(b"123456").decode("ascii")}

    denied = _get(url, headers={"If-Modified-Since": http_date()})
    assert denied.status_code == 403

    authorized = _get(url, headers=auth_headers)
    _assert_artifact_200(authorized)
    last_modified = authorized.headers["Last-Modified"]

    revalidated = _get(url, headers={**auth_headers, "If-Modified-Since": last_modified})
    _assert_304(revalidated, last_modified)


@pytest.mark.parallel
def test_published_metadata_has_no_last_modified(published_file_distribution, inline_storage):
    """Publish-generated metadata (PULP_MANIFEST) has no membership row, so no validator."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "PULP_MANIFEST")

    response = _get(url)
    assert response.status_code == 200
    assert response.content
    assert "Last-Modified" not in response.headers

    again = _get(url, headers={"If-Modified-Since": http_date()})
    assert again.status_code == 200
    assert again.content
    assert "Last-Modified" not in again.headers


@pytest.mark.parallel
def test_on_demand_304_does_not_fetch_remote(
    file_repo_with_auto_publish,
    generate_server_and_remote,
    file_bindings,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
    basic_manifest_path,
    inline_storage,
):
    """An on-demand 304 is answered from the validator without touching the remote."""
    server, remote = generate_server_and_remote(
        manifest_path=basic_manifest_path, policy="on_demand"
    )
    body = FileRepositorySyncURL(remote=remote.pulp_href)
    monitor_task(
        file_bindings.RepositoriesFileApi.sync(file_repo_with_auto_publish.pulp_href, body).task
    )
    repo = file_bindings.RepositoriesFileApi.read(file_repo_with_auto_publish.pulp_href)
    distro = file_distribution_factory(repository=repo.pulp_href)
    url = urljoin(distribution_base_url(distro.base_url), "1.iso")

    def iso_fetches():
        return [r for r in server.requests_record if "1.iso" in r.raw_path]

    assert iso_fetches() == []

    sleep(2)
    response = _get(url, headers={"If-Modified-Since": http_date()})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers.get("Last-Modified")
    assert response.headers.get("Cache-Control") == CACHE_CONTROL
    assert iso_fetches() == []


@pytest.mark.parallel
def test_matching_if_modified_since_beats_range(published_file_distribution, inline_storage):
    """A matching If-Modified-Since wins over a Range header: 304, not 206/416."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    _first, last_modified = _get_and_assert_last_modified(url)

    response = _get(url, headers={"If-Modified-Since": last_modified, "Range": "bytes=0-0"})
    _assert_304(response, last_modified)


@pytest.mark.parallel
def test_object_storage_redirect_is_not_304(published_file_distribution, object_storage_redirects):
    """Object-storage 302s carry no validator and never 304, even with If-Modified-Since."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    response = _get(url)
    assert response.status_code == 302
    assert "Last-Modified" not in response.headers
    assert "Cache-Control" not in response.headers

    again = _get(url, headers={"If-Modified-Since": http_date()})
    assert again.status_code == 302
    assert "Last-Modified" not in again.headers


@pytest.mark.parallel
def test_cold_cache_miss_with_matching_ims_304s_but_caches_200(
    published_file_distribution, inline_storage, redis_required
):
    """A conditional first request 304s from the cache miss yet still stores a full 200.

    The handler defers its own 304 to Redis when the cache is on, so make_entry builds and caches
    the 200 while the miss path answers a bodyless 304. A plain follow-up must then be a full
    cache HIT, proving the 304 was never stored as an empty entry.
    """
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    # First-ever request for this URL is conditional (cold cache).
    first = _get(url, headers={"If-Modified-Since": http_date()})
    assert first.status_code == 304
    assert first.content == b""
    last_modified = first.headers.get("Last-Modified")
    assert last_modified
    assert first.headers.get("Cache-Control") == CACHE_CONTROL

    # The miss stored a full 200, so a plain GET is a cache HIT with the same validator.
    warm = _get(url)
    _assert_artifact_200(warm)
    assert warm.headers.get("X-PULP-CACHE") == "HIT"
    assert warm.headers["Last-Modified"] == last_modified


@pytest.mark.parallel
def test_if_none_match_suppresses_304(published_file_distribution, inline_storage):
    """If-None-Match disables If-Modified-Since handling, so a match still returns a full 200."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    _first, last_modified = _get_and_assert_last_modified(url)

    response = _get(
        url, headers={"If-Modified-Since": last_modified, "If-None-Match": '"anything"'}
    )
    _assert_artifact_200(response)
    assert response.headers["Last-Modified"] == last_modified


@pytest.mark.parallel
def test_head_request_revalidates_with_304(published_file_distribution, inline_storage):
    """A conditional HEAD (as CDNs issue) sets the validator on 200 and 304s on revalidation."""
    _repo, _distro, base_url = published_file_distribution
    url = urljoin(base_url, "1.iso")

    initial = requests.head(url, allow_redirects=False)
    assert initial.status_code == 200
    last_modified = initial.headers["Last-Modified"]
    assert initial.headers.get("Cache-Control") == CACHE_CONTROL

    revalidated = requests.head(
        url, allow_redirects=False, headers={"If-Modified-Since": last_modified}
    )
    assert revalidated.status_code == 304
    assert revalidated.headers.get("Last-Modified") == last_modified
    assert revalidated.headers.get("Cache-Control") == CACHE_CONTROL
