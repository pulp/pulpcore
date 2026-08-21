

# pulpcore.plugin.content

The Content app provides built-in functionality to handle user requests for content, but in some
cases the default behavior may not work for some content types. For example, Container content requires
specific response headers to be present. In these cases the plugin write should provide a custom
Handler to the Content App by subclassing `pulpcore.plugin.content.Handler`.

Making a custom Handler is a two-step process:

1. subclass `pulpcore.plugin.content.Handler` to define your Handler's behavior
2. Add the Handler to a route using aiohttp.server's [add_route()](https://aiohttp.readthedocs.io/en/stable/web_reference.html#aiohttp.web.UrlDispatcher.add_route) interface.

If content needs to be served from within the `Distribution`'s base_path,
overriding `pulpcore.plugin.models.Distribution.content_handler`,
`content_handler_json`, and `content_handler_list_directory` is an easier
way to serve this content.

`content_handler` should return an instance of `aiohttp.web_response.Response`
or a `pulpcore.plugin.models.ContentArtifact`. It is used for the default
HTML/binary representation.

`content_handler_json` is invoked when the client's `Accept` header prefers
JSON (see `pulpcore.cache.accept_prefers_json`). Return `None` (the default)
to use pulpcore's generic paginated JSON directory listing, a JSON-serializable
dict/list, or an `aiohttp.web.StreamResponse` for full control over
headers/status. Concrete artifact paths stay binary unless this method returns
JSON. Missing/`*/*`/`text/html` Accept headers keep today's HTML/binary
responses.

The generic JSON listing envelope is:

```json
{
  "path": "/pulp/content/my-distro/",
  "packages": [{"path": "subdir/file.iso", "size": 1024, "date": "..."}],
  "count": 1,
  "limit": 1000,
  "offset": 0
}
```

Pagination uses `?limit=` and `?offset=`. The default and maximum `limit` are
`CONTENT_JSON_LISTING_DEFAULT_LIMIT` (1000) and `CONTENT_JSON_LISTING_MAX_LIMIT` (10000).
When more pages exist the body also includes `next_offset`.

## Creating your Handler

Import the Handler object through the plugin API and then subclass it. Custom functionality can be
provided by overriding the various methods of `Handler`, but here is the simplest version:

```python
from pulpcore.plugin.content import Handler

class MyHandler(Handler):

    pass
```

Here is an example of the [Container custom Handler](https://github.com/pulp/pulp_container/blob/master/pulp_container/app/registry.py).

## Registering your Handler

We register the Handler with Pulp's Content App by importing the aiohttp.server 'app' and then
adding a custom route to it. Here's an example:

```python
from pulpcore.content import app

app.add_routes([web.get(r'/my/custom/{somevar:.+}', MyHandler().stream_content)])
```

Here is an example of [Container registering some custom routes](https://github.com/pulp/pulp_container/blob/master/pulp_container/app/content.py).

## Restricting which detail Distributions Match

To restrict which Distribution model types your Handler will serve, set the `distribution_model`
field to your Model type. This causes the Handler to only search/serve your Distribution types.

```python
from pulpcore.plugin.content import Handler

from models import MyDistribution


class MyHandler(Handler):

    distribution_model = MyDistribution
```

## pulpcore.plugin.content.Handler

::: pulpcore.plugin.content.Handler
