# Create client bindings

!!! warning "Update Docs"
    This should be targeted at creating bindings, as we don't intend to keep maintaining the bindings as packages.

## Python Client for pulpcore's REST API

The `pulpcore-client` Python package is available on [PyPI](https://pypi.org/project/pulpcore-client/). It is currently published daily and with every RC.
Each plugin is responsible for publishing it's own client to PyPI. The client libraries for plugins
should follow the\`\`pulp\_\<slug>-client\`\` naming scheme.

## Ruby Client for pulpcore's REST API

`pulpcore_client` Ruby Gem is available on
[rubygems.org](https://rubygems.org/gems/pulpcore_client). It is currently published daily and
with every RC. Each plugin is responsible for publishing it's own client to Rubygems.org. The
client libraries for plugins should follow the\`\`pulp\_\<slug>\_client\`\` naming scheme.

## Other Languages

A client can be generated using Pulp's OpenAPI schema and any of the available
[generators](https://openapi-generator.tech/docs/generators/).

Generating a client is a two step process:

**1) Download the OpenAPI schema for pulpcore:**

```bash
curl -o api.json http://<pulp-hostname>:24817/pulp/api/v3/docs/api.json?bindings&component=core
```

The OpenAPI schema for a specific plugin can be downloaded by specifying the plugin's module name
as a GET parameter. For example for pulp_rpm only endpoints use a query like this:

```bash
curl -o api.json http://<pulp-hostname>:24817/pulp/api/v3/docs/api.json?bindings&component=rpm
```

**2) Generate a client using openapi-generator.**

The schema can then be used as input to the openapi-generator-cli. The documentation on getting
started with openapi-generator-cli is available on
[openapi-generator.tech](https://openapi-generator.tech/#try).
