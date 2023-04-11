"""Tests for Pulp 3's authentication API.

For more information, see the documentation on `Authentication
<https://docs.pulpproject.org/restapi.html#section/Authentication>`_.
"""
import pytest
import json

from pulpcore.client.pulpcore import ApiException


@pytest.mark.parallel
def test_base_auth_success(artifacts_api_client, pulp_admin_user):
    """Perform HTTP basic authentication with valid credentials.

    Assert that a response indicating success is returned.
    """
    with pulp_admin_user:
        response, status, headers = artifacts_api_client.list_with_http_info()
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    # Maybe test correlation ID as well?


@pytest.mark.parallel
def test_base_auth_failure(artifacts_api_client, invalid_user):
    """Perform HTTP basic authentication with invalid credentials.

    Assert that a response indicating failure is returned.
    """
    with invalid_user:
        with pytest.raises(ApiException) as e:
            artifacts_api_client.list()

    assert e.value.status == 401
    response = json.loads(e.value.body)
    response_detail = response["detail"].lower()
    for key in ("invalid", "username", "password"):
        assert key in response_detail


@pytest.mark.parallel
def test_base_auth_required(artifacts_api_client, anonymous_user):
    """Perform HTTP basic authentication with no credentials.

    Asert that a response indicating failure is returned.
    """
    with anonymous_user:
        with pytest.raises(ApiException) as e:
            artifacts_api_client.list()

    assert e.value.status == 401
    response = json.loads(e.value.body)
    response_detail = response["detail"].lower()
    for key in ("authentication", "credentials", "provided"):
        assert key in response_detail
