"""
Customizing OpenAPI validation.

OpenAPI requires paths to start with slashes:
https://spec.openapis.org/oas/v3.0.3#patterned-fields

But some pulp paths start with curly brackets e.g. {artifact_href}
This script modifies drf-spectacular schema validation to accept slashes and curly brackets.
"""

import json
from drf_spectacular.validation import JSON_SCHEMA_SPEC_PATH

with open(JSON_SCHEMA_SPEC_PATH) as fh:
    openapi3_schema_spec = json.load(fh)

properties = openapi3_schema_spec["definitions"]["Paths"]["patternProperties"]
# Making OpenAPI validation to accept paths starting with / and {
if "^\\/|{" not in properties:
    properties["^\\/|{"] = properties["^\\/"]
    del properties["^\\/"]

with open(JSON_SCHEMA_SPEC_PATH, "w") as fh:
    json.dump(openapi3_schema_spec, fh)
