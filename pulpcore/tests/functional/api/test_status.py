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
                "total": {"type": "integer"},
                "used": {"type": "integer"},
                "free": {"type": "integer"},
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


@pytest.fixture(scope="module")
def expected_pulp_status_schema():
    """Returns the expected status response."""
    if settings.DEFAULT_FILE_STORAGE != "pulpcore.app.models.storage.FileSystem":
        STATUS["properties"]["storage"].pop("properties")
        STATUS["properties"]["storage"]["type"] = "null"

    return STATUS


@pytest.mark.parallel
def test_get_authenticated(status_api_client, expected_pulp_status_schema):
    """GET the status path with valid credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    response = status_api_client.status_read()
    verify_get_response(response.to_dict(), expected_pulp_status_schema)


@pytest.mark.parallel
def test_get_unauthenticated(status_api_client, anonymous_user, expected_pulp_status_schema):
    """GET the status path with no credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    with anonymous_user:
        response = status_api_client.status_read()
    verify_get_response(response.to_dict(), expected_pulp_status_schema)


@pytest.mark.parallel
def test_post_authenticated(status_api_client, pulpcore_client, pulp_api_v3_url):
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
        pulpcore_client.request("POST", status_url)

    assert e.value.status == 405


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
