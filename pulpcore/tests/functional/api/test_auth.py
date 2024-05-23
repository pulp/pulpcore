"""Tests for Pulp 3's authentication API.

For more information, see the documentation on `Authentication
<https://docs.pulpproject.org/restapi.html#section/Authentication>`_.
"""

import pytest
import json

from base64 import b64encode
from pulpcore.client.pulpcore import ApiException

from pulpcore.app import settings


@pytest.mark.parallel
def test_base_auth_success(pulpcore_bindings, pulp_admin_user):
    """Perform HTTP basic authentication with valid credentials.

    Assert that a response indicating success is returned.
    """
    with pulp_admin_user:
        response, status, headers = pulpcore_bindings.ArtifactsApi.list_with_http_info()
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    # Maybe test correlation ID as well?


@pytest.mark.parallel
def test_base_auth_failure(pulpcore_bindings, invalid_user):
    """Perform HTTP basic authentication with invalid credentials.

    Assert that a response indicating failure is returned.
    """
    with invalid_user:
        with pytest.raises(ApiException) as e:
            pulpcore_bindings.ArtifactsApi.list()

    assert e.value.status == 401
    response = json.loads(e.value.body)
    response_detail = response["detail"].lower()
    for key in ("invalid", "username", "password"):
        assert key in response_detail


@pytest.mark.parallel
def test_base_auth_required(pulpcore_bindings, anonymous_user):
    """Perform HTTP basic authentication with no credentials.

    Assert that a response indicating failure is returned.
    """
    with anonymous_user:
        with pytest.raises(ApiException) as e:
            pulpcore_bindings.ArtifactsApi.list()

    assert e.value.status == 401
    response = json.loads(e.value.body)
    response_detail = response["detail"].lower()
    for key in ("authentication", "credentials", "provided"):
        assert key in response_detail


@pytest.mark.parallel
@pytest.mark.skipif(
    "django.contrib.auth.backends.RemoteUserBackend" not in settings.AUTHENTICATION_BACKENDS
    and "pulpcore.app.authentication.JSONHeaderRemoteAuthentication"
    not in settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
    reason="Test can't run unless RemoteUserBackend and JSONHeaderRemoteAuthentication are enabled",
)
def test_jq_header_remote_auth(pulpcore_bindings, anonymous_user):
    """Perform a Authentication using an specific header.

    Assert that a user is extracted from the expected header.
    """

    with anonymous_user:
        username = anonymous_user._saved_credentials[0][0]
        header_content = json.dumps({"identity": {"user": {"username": username}}})
        encoded_header = b64encode(bytes(header_content, "ascii"))

        pulpcore_bindings.ArtifactsApi.api_client.default_headers["x-rh-identity"] = encoded_header
        _, status, _ = pulpcore_bindings.ArtifactsApi.list_with_http_info()
    assert status == 200


@pytest.mark.parallel
@pytest.mark.skipif(
    "django.contrib.auth.backends.RemoteUserBackend" not in settings.AUTHENTICATION_BACKENDS
    and "pulpcore.app.authentication.JSONHeaderRemoteAuthentication"
    not in settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
    reason="Test can't run unless RemoteUserBackend and JSONHeaderRemoteAuthentication are enabled",
)
def test_jq_header_remote_auth_denied_by_wrong_header(pulpcore_bindings, anonymous_user):
    """Perform a Authentication using an specific header.

    Assert that an invalid header or invalid JQ path denies the access.
    """

    with anonymous_user:
        username = anonymous_user._saved_credentials[0][0]
        header_content = json.dumps({"identity": {"user": {"username": username}}})
        encoded_header = b64encode(bytes(header_content, "ascii"))

        pulpcore_bindings.ArtifactsApi.api_client.default_headers.pop("x-rh-identity", None)
        pulpcore_bindings.ArtifactsApi.api_client.default_headers["x-something-identity"] = (
            encoded_header
        )

        with pytest.raises(ApiException) as exception:
            pulpcore_bindings.ArtifactsApi.list()

    assert exception.value.status == 401


@pytest.mark.parallel
@pytest.mark.skipif(
    "django.contrib.auth.backends.RemoteUserBackend" not in settings.AUTHENTICATION_BACKENDS
    and "pulpcore.app.authentication.JSONHeaderRemoteAuthentication"
    not in settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
    reason="Test can't run unless RemoteUserBackend and JSONHeaderRemoteAuthentication are enabled",
)
def test_jq_header_remote_auth_denied_by_wrong_content(pulpcore_bindings, anonymous_user):
    with anonymous_user:
        username = anonymous_user._saved_credentials[0][0]
        header_content = json.dumps({"identity": {"username": {"username": username}}})
        encoded_header = b64encode(bytes(header_content, "ascii"))

        pulpcore_bindings.ArtifactsApi.api_client.default_headers["x-rh-identity"] = encoded_header

        with pytest.raises(ApiException) as exception:
            pulpcore_bindings.ArtifactsApi.list()

    assert exception.value.status == 401
