Added Distribution.content_headers_for() to let plugins affect content-app response headers.

This can be useful, for example, when it's desirable for specific files to
be served with Cache-control: no-cache.

