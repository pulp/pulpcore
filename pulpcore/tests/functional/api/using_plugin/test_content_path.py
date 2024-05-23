"""Tests related to content path."""

import pytest
import uuid

from urllib.parse import urljoin


from pulpcore.tests.functional.utils import get_from_url


@pytest.mark.parallel
def test_content_directory_listing(
    pulpcore_bindings,
    file_distribution_factory,
    gen_object_with_cleanup,
    pulp_settings,
    http_get,
    pulp_status,
):
    """Checks that distributions are grouped by base-path when listing content directories."""

    HIDE_GUARDED_DISTRIBUTIONS = getattr(pulp_settings, "HIDE_GUARDED_DISTRIBUTIONS", False)

    content_guard1 = gen_object_with_cleanup(
        pulpcore_bindings.ContentguardsRbacApi, {"name": str(uuid.uuid4())}
    )

    base_path = str(uuid.uuid4())
    for path, content_guard in [
        ("/foo1", None),
        ("/foo2", content_guard1.pulp_href),
        ("/boo1/foo1", None),
        ("/boo2/foo1", content_guard1.pulp_href),
    ]:
        file_distribution_factory(base_path=base_path + path, content_guard=content_guard)

    base_url = urljoin(
        pulp_status.content_settings.content_origin,
        pulp_status.content_settings.content_path_prefix,
    )
    if pulp_settings.DOMAIN_ENABLED:
        base_url = urljoin(base_url, "default/")
    response = http_get(base_url).decode("utf-8")
    assert response.count(f'a href="{base_path}/"') == 1
    assert response.count('a href="../"') == 0

    url = urljoin(base_url, base_path + "/")
    response = http_get(url).decode("utf-8")
    assert response.count('a href="foo1/"') == 1
    assert response.count('a href="foo2/"') == (0 if HIDE_GUARDED_DISTRIBUTIONS else 1)
    assert response.count('a href="boo1/"') == 1
    assert response.count('a href="boo2/"') == (0 if HIDE_GUARDED_DISTRIBUTIONS else 1)
    assert response.count('a href="../"') == 1

    response = http_get(urljoin(url, "boo1/")).decode("utf-8")
    assert response.count('a href="foo1/"') == 1

    # Assert that not using a trailing slash on the root returns a 301
    base_url = urljoin(
        pulp_status.content_settings.content_origin,
        pulp_status.content_settings.content_path_prefix,
    )
    if pulp_settings.DOMAIN_ENABLED:
        base_url = urljoin(base_url, "default/")
    response = get_from_url(base_url[:-1])
    assert response.history[0].status == 301
    assert response.status == 200

    # Assert that not using a trailing slash returns a 301 for a partial base path
    url = urljoin(base_url, base_path)
    response = get_from_url(url)
    assert response.history[0].status == 301
    assert response.status == 200

    # Assert that not using a trailing slash within a distribution returns a 301
    url = f"{url}/boo1"
    response = get_from_url(url)
    assert response.history[0].status == 301
    assert response.status == 200

    # Assert that not using a trailing slash for a full base path returns a 301
    url = f"{url}/foo1"
    response = get_from_url(url)
    assert response.history[0].status == 301
    assert response.status == 404
    assert "Distribution is not pointing to" in response.reason

    # Assert that a non-existing base path does not return a 301
    url = url[:-1]
    response = get_from_url(url)
    assert len(response.history) == 0
    assert response.status == 404
