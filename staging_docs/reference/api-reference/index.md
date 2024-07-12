

# Plugin API Reference

The Plugin API is versioned in sync with `pulpcore` and consists of everything importable within
the {mod}`pulpcore.plugin` namespace. It is governed by the
[deprecation policy](site:pulpcore/docs/dev/learn/plugin-concepts/?h=deprecation#plugin-api-stability-and-deprecation-policy).
When writing plugins, care should be taken to only import `pulpcore` components exposed in this
namespace; importing from elsewhere within the `pulpcore` module (e.g. importing directly from
`pulpcore.app`, `pulpcore.exceptions`, etc.) is unsupported, and not protected by the
aforementioned Pulp Plugin API deprecation policy.

```{toctree}
models
exceptions
serializers
storage
viewsets
tasking
download
stages
content-app
util
```

```{eval-rst}
.. automodule:: pulpcore.plugin
    :imported-members:
    :members:
```
