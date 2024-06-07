"""Test related to the openapi schema Pulp generates."""

import copy
import json
import os

import requests
import pytest
import jsonschema

from drf_spectacular import validation
from collections import defaultdict

JSON_SCHEMA_SPEC_PATH = os.path.join(
    os.path.dirname(validation.__file__), "openapi_3_0_schema.json"
)


@pytest.fixture(scope="session")
def openapi3_schema_spec():
    with open(JSON_SCHEMA_SPEC_PATH) as fh:
        openapi3_schema_spec = json.load(fh)

    return openapi3_schema_spec


@pytest.fixture(scope="session")
def openapi3_schema_with_modified_safe_chars(openapi3_schema_spec):
    openapi3_schema_spec_copy = copy.deepcopy(openapi3_schema_spec)  # Don't modify the original
    # Making OpenAPI validation to accept paths starting with / and {
    properties = openapi3_schema_spec_copy["definitions"]["Paths"]["patternProperties"]
    properties["^\\/|{"] = properties["^\\/"]
    del properties["^\\/"]

    return openapi3_schema_spec_copy


@pytest.fixture(scope="session")
def pulp_openapi_schema_url(pulp_api_v3_url):
    return f"{pulp_api_v3_url}docs/api.json"


@pytest.fixture(scope="session")
def pulp_openapi_schema(pulp_openapi_schema_url):
    return requests.get(pulp_openapi_schema_url).json()


@pytest.fixture(scope="session")
def pulp_openapi_schema_pk_path_set(pulp_openapi_schema_url):
    return requests.get(f"{pulp_openapi_schema_url}?pk_path=1").json()


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_valid_with_pk_path_set(pulp_openapi_schema_pk_path_set, openapi3_schema_spec):
    jsonschema.validate(instance=pulp_openapi_schema_pk_path_set, schema=openapi3_schema_spec)


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_invalid_default_schema(pulp_openapi_schema, openapi3_schema_spec):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=pulp_openapi_schema, schema=openapi3_schema_spec)


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_valid_with_safe_chars(pulp_openapi_schema, openapi3_schema_with_modified_safe_chars):
    jsonschema.validate(
        instance=pulp_openapi_schema, schema=openapi3_schema_with_modified_safe_chars
    )


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_no_dup_operation_ids(pulp_openapi_schema):
    paths = pulp_openapi_schema["paths"]
    operation_ids = defaultdict(int)
    for p in paths.values():
        for operation in p.values():
            operation_ids[operation["operationId"]] += 1

    dup_ids = [id for id, cnt in operation_ids.items() if cnt > 1]
    assert len(dup_ids) == 0, f"Duplicate operationIds found: {dup_ids}"


@pytest.mark.parallel
def test_external_auth_on_security_scheme(pulp_settings, pulp_openapi_schema):
    if (
        "django.contrib.auth.backends.RemoteUserBackend"
        not in pulp_settings.AUTHENTICATION_BACKENDS
        or "pulpcore.app.authentication.JSONHeaderRemoteAuthentication"
        not in pulp_settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
    ):
        pytest.skip(
            "Test can't run unless RemoteUserBackend and JSONHeaderRemoteAuthentication are enabled"
        )

    security_schemes = pulp_openapi_schema["components"]["securitySchemes"]
    assert "json_header_remote_authentication" in security_schemes

    security_scheme = security_schemes["json_header_remote_authentication"]
    assert pulp_settings.AUTHENTICATION_JSON_HEADER_OPENAPI_SECURITY_SCHEME == security_scheme
