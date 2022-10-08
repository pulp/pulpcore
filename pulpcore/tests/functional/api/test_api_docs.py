"""Tests related to the api docs page."""
import pytest
from pulpcore.client.pulpcore import ApiException


@pytest.fixture(scope="session")
def pulp_docs_url(pulp_api_v3_url):
    return f"{pulp_api_v3_url}docs/"


@pytest.mark.parallel
def test_valid_credentials(pulpcore_client, pulp_docs_url):
    """Get API documentation with valid credentials.

    Assert the API documentation is returned.
    """
    response = pulpcore_client.request("GET", pulp_docs_url)
    assert response.status == 200


@pytest.mark.parallel
def test_no_credentials(pulpcore_client, pulp_docs_url, anonymous_user):
    """Get API documentation with no credentials.

    Assert the API documentation is returned.
    """
    with anonymous_user:
        response = pulpcore_client.request("GET", pulp_docs_url)
        assert response.status == 200


@pytest.mark.parallel
def test_http_method(pulpcore_client, pulp_docs_url):
    """Get API documentation with an HTTP method other than GET.

    Assert an error is returned.
    """
    with pytest.raises(ApiException) as e:
        pulpcore_client.request("POST", pulp_docs_url)

    assert e.value.status == 405
