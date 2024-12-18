"""Tests related to the api docs page."""

import pytest


@pytest.fixture(scope="session")
def pulp_docs_url(pulp_api_v3_url):
    return f"{pulp_api_v3_url}docs/"


@pytest.mark.parallel
def test_valid_credentials(pulpcore_bindings, pulp_docs_url):
    """Get API documentation with valid credentials.

    Assert the API documentation is returned.
    """
    response = pulpcore_bindings.client.rest_client.request("GET", pulp_docs_url)
    assert response.status == 200


@pytest.mark.parallel
def test_no_credentials(pulpcore_bindings, pulp_docs_url, anonymous_user):
    """Get API documentation with no credentials.

    Assert the API documentation is returned.
    """
    with anonymous_user:
        response = pulpcore_bindings.client.rest_client.request("GET", pulp_docs_url)
        assert response.status == 200


@pytest.mark.parallel
def test_http_method(pulpcore_bindings, pulp_docs_url):
    """Get API documentation with an HTTP method other than GET.

    Assert an error is returned.
    """
    response = pulpcore_bindings.client.rest_client.request("POST", pulp_docs_url)

    assert response.status == 405
