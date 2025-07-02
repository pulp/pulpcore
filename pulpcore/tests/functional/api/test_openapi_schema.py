"""Test related to the openapi schema Pulp generates."""

import copy
import json
from pathlib import Path

import pytest
import jsonschema

from drf_spectacular import validation
from collections import defaultdict


@pytest.fixture(scope="session")
def openapi3_schema_spec(pulp_openapi_schema):
    schema_version = pulp_openapi_schema["openapi"]
    if schema_version.startswith("3.0"):
        spec_path = Path(validation.__file__).parent / "openapi_3_0_schema.json"
    elif schema_version.startswith("3.1"):
        spec_path = Path(validation.__file__).parent / "openapi_3_1_schema.json"
    else:
        pytest.fail(f"Unknown OpenAPI schema version [{schema_version}].")
    return json.loads(spec_path.read_text())


@pytest.fixture(scope="session")
def openapi3_schema_with_modified_safe_chars(openapi3_schema_spec):
    oas_copy = copy.deepcopy(openapi3_schema_spec)  # Don't modify the original
    # Making OpenAPI validation to accept paths starting with / and {
    if "3.1.x" in oas_copy["description"]:
        pattern_properties = oas_copy["$defs"]["paths"]["patternProperties"]
        pattern_properties["^/|{"] = pattern_properties.pop("^/")
    else:
        pattern_properties = oas_copy["definitions"]["Paths"]["patternProperties"]
        pattern_properties["^\\/|{"] = pattern_properties.pop("^\\/")

    return oas_copy


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


@pytest.mark.parallel
def test_content_in_filter_is_array(pulp_openapi_schema):
    tested = []
    for name, path in pulp_openapi_schema["paths"].items():
        if name.endswith("repository_versions/") or name.endswith("publications/"):
            tested.append(name)
            for parameter in path["get"]["parameters"]:
                if parameter["name"] == "content__in":
                    schema = parameter["schema"]
                    assert schema["type"] == "array"
                    assert schema["items"]["type"] == "string"
                    break
            else:
                assert False, "Couldn't find the content__in filter!"
    assert len(tested) == 2, "Couldn't test both the Publication and RepositoryVersion endpoints"
