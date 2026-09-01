"""Tests for content-app Accept negotiation and JSON directory listing."""

import json
from urllib.parse import urljoin

import pytest
import requests
from django.conf import settings

from pulpcore.tests.functional.utils import download_file

JSON_ACCEPT = {"Accept": "application/json"}
HTML_ACCEPT = {"Accept": "text/html"}


def _add_files_to_repo(file_bindings, repo, contents, monitor_task):
    monitor_task(
        file_bindings.RepositoriesFileApi.modify(
            repo.pulp_href,
            {"add_content_units": [content.pulp_href for content in contents]},
        ).task
    )
    return file_bindings.RepositoriesFileApi.read(repo.pulp_href)


@pytest.mark.parallel
def test_json_vs_html_listing_and_artifact(
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
):
    """JSON listing is recursive; default Accept stays HTML; artifacts stay binary."""
    root_file = file_content_unit_with_name_factory("a.iso")
    nested_file = file_content_unit_with_name_factory("subdir/b.iso")
    repo = _add_files_to_repo(
        file_bindings,
        file_repo_with_auto_publish,
        [root_file, nested_file],
        monitor_task,
    )
    distro = file_distribution_factory(repository=repo.pulp_href)
    distro_url = distribution_base_url(distro.base_url)

    json_listing = download_file(distro_url, headers=JSON_ACCEPT)
    assert "application/json" in json_listing.response_obj.headers["Content-Type"]
    assert json_listing.response_obj.headers.get("Vary") == "Accept"
    body = json.loads(json_listing.body)
    assert body["path"].rstrip("/").endswith(distro.base_path)
    listed_paths = [pkg["path"] for pkg in body["packages"]]
    assert "a.iso" in listed_paths
    assert "subdir/b.iso" in listed_paths
    assert "subdir/" not in listed_paths
    assert body["count"] == len(body["packages"])
    assert body["limit"] == settings.CONTENT_JSON_LISTING_DEFAULT_LIMIT
    assert body["offset"] == 0
    assert "next_offset" not in body

    html_listing = download_file(distro_url, headers=HTML_ACCEPT)
    html = html_listing.body.decode("utf-8")
    assert "text/html" in html_listing.response_obj.headers["Content-Type"]
    assert html_listing.response_obj.headers.get("Vary") == "Accept"
    assert '<a href="./a.iso">' in html
    assert '<a href="./subdir/">' in html
    assert "./subdir/b.iso" not in html

    default_listing = download_file(distro_url)
    assert "text/html" in default_listing.response_obj.headers["Content-Type"]

    artifact = download_file(urljoin(distro_url, "a.iso"), headers=JSON_ACCEPT)
    assert "application/json" not in artifact.response_obj.headers.get("Content-Type", "")
    assert artifact.body != json_listing.body


@pytest.mark.parallel
def test_json_listing_pagination_and_invalid_params(
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
):
    contents = [file_content_unit_with_name_factory(f"{i}.iso") for i in range(3)]
    repo = _add_files_to_repo(file_bindings, file_repo_with_auto_publish, contents, monitor_task)
    distro = file_distribution_factory(repository=repo.pulp_href)
    distro_url = distribution_base_url(distro.base_url)

    page = json.loads(download_file(f"{distro_url}?limit=1&offset=0", headers=JSON_ACCEPT).body)
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert len(page["packages"]) == 1
    assert page["count"] >= 3
    assert page["next_offset"] == 1

    next_page = json.loads(
        download_file(
            f"{distro_url}?limit=1&offset={page['next_offset']}", headers=JSON_ACCEPT
        ).body
    )
    assert next_page["offset"] == 1
    assert next_page["packages"][0]["path"] != page["packages"][0]["path"]

    invalid = json.loads(
        download_file(f"{distro_url}?limit=nope&offset=nope", headers=JSON_ACCEPT).body
    )
    assert invalid["limit"] == settings.CONTENT_JSON_LISTING_DEFAULT_LIMIT
    assert invalid["offset"] == 0


@pytest.mark.parallel
def test_json_listing_trailing_slash_redirect(
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
):
    nested = file_content_unit_with_name_factory("subdir/b.iso")
    repo = _add_files_to_repo(file_bindings, file_repo_with_auto_publish, [nested], monitor_task)
    distro = file_distribution_factory(repository=repo.pulp_href)
    distro_url = distribution_base_url(distro.base_url)
    no_slash_url = urljoin(distro_url, "subdir")

    redirect = requests.get(no_slash_url, headers=JSON_ACCEPT, allow_redirects=False, verify=False)
    assert redirect.status_code == 301
    assert redirect.headers["Location"].endswith("subdir/")

    listed = download_file(urljoin(distro_url, "subdir/"), headers=JSON_ACCEPT)
    body = json.loads(listed.body)
    assert body["packages"]
    assert body["packages"][0]["path"] == "b.iso"


@pytest.mark.parallel
def test_json_and_html_listings_are_cached_separately(
    file_bindings,
    file_repo_with_auto_publish,
    file_content_unit_with_name_factory,
    file_distribution_factory,
    distribution_base_url,
    monitor_task,
    redis_status,
):
    if not redis_status:
        pytest.skip("Redis is not enabled; this test requires the content-app cache")

    content = file_content_unit_with_name_factory("a.iso")
    repo = _add_files_to_repo(file_bindings, file_repo_with_auto_publish, [content], monitor_task)
    distro = file_distribution_factory(repository=repo.pulp_href)
    distro_url = distribution_base_url(distro.base_url)

    json_miss = download_file(distro_url, headers=JSON_ACCEPT)
    json_hit = download_file(distro_url, headers=JSON_ACCEPT)
    html_miss = download_file(distro_url, headers=HTML_ACCEPT)
    html_hit = download_file(distro_url, headers=HTML_ACCEPT)

    assert json_miss.response_obj.headers.get("X-PULP-CACHE") == "MISS"
    assert json_hit.response_obj.headers.get("X-PULP-CACHE") == "HIT"
    assert html_miss.response_obj.headers.get("X-PULP-CACHE") == "MISS"
    assert html_hit.response_obj.headers.get("X-PULP-CACHE") == "HIT"
    assert "application/json" in json_hit.response_obj.headers["Content-Type"]
    assert "text/html" in html_hit.response_obj.headers["Content-Type"]
    assert json.loads(json_hit.body)["packages"]
    assert b"<html" in html_hit.body.lower() or b"<a href=" in html_hit.body.lower()
