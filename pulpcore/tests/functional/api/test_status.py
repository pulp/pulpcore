"""Test the status page."""

import pytest

from jsonschema import validate


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
                "content_origin": {"type": ["string", "null"]},
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
def test_get_authenticated(test_path, pulpcore_bindings, pulp_settings):
    """GET the status path with valid credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    response = pulpcore_bindings.StatusApi.status_read()
    verify_get_response(response.to_dict(), STATUS, pulp_settings)


@pytest.mark.parallel
def test_get_unauthenticated(test_path, pulpcore_bindings, anonymous_user, pulp_settings):
    """GET the status path with no credentials.

    Verify the response with :meth:`verify_get_response`.
    """
    with anonymous_user:
        response = pulpcore_bindings.StatusApi.status_read()
    verify_get_response(response.to_dict(), STATUS, pulp_settings)


@pytest.mark.parallel
def test_post_authenticated(
    test_path,
    pulp_api_v3_path,
    pulp_api_v3_url,
    pulpcore_bindings,
):
    """POST the status path with valid credentials.

    Assert an error is returned.
    """
    # Ensure bindings doesn't have a "post" method
    attrs = dir(pulpcore_bindings.StatusApi)
    for post_attr in ("create", "post", "status_post", "status_create"):
        assert post_attr not in attrs
    # Try anyway to POST to /status/
    status_url = f"{pulp_api_v3_url}status/"
    response = pulpcore_bindings.client.rest_client.request(
        "POST", status_url, headers={"User-Agent": test_path}
    )
    assert response.status == 405


@pytest.mark.parallel
def test_storage_per_domain(
    pulpcore_bindings,
    pulp_api_v3_url,
    domain_factory,
    random_artifact_factory,
):
    """Tests that the storage property returned in status is valid per domain."""
    domain = domain_factory()
    # Status endpoint is not exposed at domain url in API spec to prevent duplicates, call manually
    status_url = f"{pulp_api_v3_url}status/".replace("default", domain.name)
    status_response = pulpcore_bindings.client.rest_client.request("GET", status_url)
    domain_status = pulpcore_bindings.client.deserialize(
        status_response.response.data, "StatusResponse", "application/json"
    )
    assert domain_status.storage.used == 0

    random_artifact_factory(size=1, pulp_domain=domain.name)
    status_response = pulpcore_bindings.client.rest_client.request("GET", status_url)
    domain_status = pulpcore_bindings.client.deserialize(
        status_response.response.data, "StatusResponse", "application/json"
    )

    assert domain_status.storage.used == 1

    default_status = pulpcore_bindings.StatusApi.status_read()
    assert default_status.storage != domain_status.storage


def verify_get_response(status, expected_schema, settings):
    """Verify the response to an HTTP GET call.

    Verify that several attributes and have the correct type or value.
    """
    validate(status, expected_schema)
    assert status["database_connection"]["connected"]
    assert status["online_workers"] != []
    assert status["versions"] != []

    assert status["content_settings"] is not None
    assert status["content_settings"]["content_path_prefix"] is not None

    assert status["storage"]["used"] is not None
    if settings.STORAGES["default"]["BACKEND"] != "pulpcore.app.models.storage.FileSystem":
        assert status["storage"]["free"] is None
        assert status["storage"]["total"] is None
    else:
        assert status["storage"]["free"] is not None
        assert status["storage"]["total"] is not None


@pytest.mark.parallel
def test_livez_unauthenticated(
    pulpcore_bindings,
    anonymous_user,
):
    """
    Assert that GET requests to Livez API return 200 without a response body.
    """
    with anonymous_user:
        assert pulpcore_bindings.LivezApi.livez_read() is None
