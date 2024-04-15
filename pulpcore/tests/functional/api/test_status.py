"""Test the status page."""

import pytest

from django.conf import settings
from jsonschema import validate
from pulpcore.client.pulpcore import ApiException


STATUS = {
    "$schema": "http://json-schema.org/schema#",
    "title": "Pulp 3 status API schema",
    "description": ("Derived from Pulp's actual behaviour and various Pulp issues."),
    "type": "object",
    "properties": {
        "database_connection": {
            "type": "object",
            "properties": {"connected": {"type": "boolean"}},
        },
        "redis_connection": {"type": "object", "properties": {"connected": {"type": "boolean"}}},
        "missing_workers": {"type": "array", "items": {"type": "object"}},
        "online_workers": {"type": "array", "items": {"type": "object"}},
        "versions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "version": {"type": "string"},
                    "package": {"type": "string"},
                },
            },
        },
        "storage": {
            "type": "object",
            "properties": {
                "total": {"type": ["integer", "null"]},
                "used": {"type": ["integer", "null"]},
                "free": {"type": ["integer", "null"]},
            },
        },
        "content_settings": {
            "type": "object",
            "properties": {
                "content_origin": {"type": "string"},
                "content_path_prefix": {"type": "string"},
            },
            "required": ["content_origin", "content_path_prefix"],
        },
    },
    "required": [
        "content_settings",
        "database_connection",
        "online_workers",
        "storage",
        "versions",
    ],
}


@pytest.mark.parallel
def test_get_authenticated(test_path, status_api_client, received_otel_span):
    """GET the status path with valid credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    response = status_api_client.status_read()
    verify_get_response(response.to_dict(), STATUS)
    assert received_otel_span(
        {
            "http.method": "GET",
            "http.target": "/pulp/api/v3/status/",
            "http.status_code": 200,
            "http.user_agent": test_path,
        }
    )


@pytest.mark.parallel
def test_get_unauthenticated(test_path, status_api_client, anonymous_user, received_otel_span):
    """GET the status path with no credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    with anonymous_user:
        response = status_api_client.status_read()
    verify_get_response(response.to_dict(), STATUS)
    assert received_otel_span(
        {
            "http.method": "GET",
            "http.target": "/pulp/api/v3/status/",
            "http.status_code": 200,
            "http.user_agent": test_path,
        }
    )


@pytest.mark.parallel
def test_post_authenticated(
    test_path,
    pulp_api_v3_path,
    status_api_client,
    pulpcore_bindings,
    pulp_api_v3_url,
    received_otel_span,
):
    """POST the status path with valid credentials.

    Assert an error is returned.
    """
    # Ensure bindings doesn't have a "post" method
    attrs = dir(status_api_client)
    for post_attr in ("create", "post", "status_post", "status_create"):
        assert post_attr not in attrs
    # Try anyway to POST to /status/
    status_url = f"{pulp_api_v3_url}status/"
    with pytest.raises(ApiException) as e:
        pulpcore_bindings.client.request("POST", status_url, headers={"User-Agent": test_path})

    assert e.value.status == 405
    assert received_otel_span(
        {
            "http.method": "POST",
            "http.target": f"{pulp_api_v3_path}status/",
            "http.status_code": 405,
            "http.user_agent": test_path,
        }
    )


@pytest.mark.parallel
def test_storage_per_domain(
    status_api_client,
    pulpcore_bindings,
    pulp_api_v3_url,
    domain_factory,
    random_artifact_factory,
):
    """Tests that the storage property returned in status is valid per domain."""
    domain = domain_factory()
    # Status endpoint is not exposed at domain url in API spec to prevent duplicates, call manually
    status_url = f"{pulp_api_v3_url}status/".replace("default", domain.name)
    status_response = pulpcore_bindings.client.request("GET", status_url)
    domain_status = pulpcore_bindings.client.deserialize(status_response, "StatusResponse")
    assert domain_status.storage.used == 0

    random_artifact_factory(size=1, pulp_domain=domain.name)
    status_response = pulpcore_bindings.client.request("GET", status_url)
    domain_status = pulpcore_bindings.client.deserialize(status_response, "StatusResponse")

    assert domain_status.storage.used == 1

    default_status = status_api_client.status_read()
    assert default_status.storage != domain_status.storage


def verify_get_response(status, expected_schema):
    """Verify the response to an HTTP GET call.

    Verify that several attributes and have the correct type or value.
    """
    validate(status, expected_schema)
    assert status["database_connection"]["connected"]
    assert status["online_workers"] != []
    assert status["versions"] != []

    assert status["content_settings"] is not None
    assert status["content_settings"]["content_origin"] is not None
    assert status["content_settings"]["content_path_prefix"] is not None

    assert status["storage"]["used"] is not None
    if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
        assert status["storage"]["free"] is None
        assert status["storage"]["total"] is None
    else:
        assert status["storage"]["free"] is not None
        assert status["storage"]["total"] is not None
