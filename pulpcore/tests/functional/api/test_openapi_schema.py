"""Test related to the openapi schema Pulp generates."""
import asyncio
import copy
import json

import aiohttp
import pytest
import jsonschema

from drf_spectacular.validation import JSON_SCHEMA_SPEC_PATH
from jsonschema import ValidationError
from collections import defaultdict


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
    return asyncio.run(_download_schema(pulp_openapi_schema_url))


@pytest.fixture(scope="session")
def pulp_openapi_schema_pk_path_set(pulp_openapi_schema_url):
    url = f"{pulp_openapi_schema_url}?pk_path=1"
    return asyncio.run(_download_schema(url))


async def _download_schema(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_valid_with_pk_path_set(pulp_openapi_schema_pk_path_set, openapi3_schema_spec):
    jsonschema.validate(instance=pulp_openapi_schema_pk_path_set, schema=openapi3_schema_spec)


@pytest.mark.parallel
@pytest.mark.from_pulpcore_for_all_plugins
def test_invalid_default_schema(pulp_openapi_schema, openapi3_schema_spec):
    with pytest.raises(ValidationError):
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
