# CDN Caching

Pulp's content app implements some behavior to help with external caching processes.

## Cache Validation

For most requests, the Content App returns [`Last-Modified`][last-modified] and [`ETag`][etag] headers for the requested resource; the ETag is usually a digest.
[Shared caches][cache-types], such as CDNs, and private caches, such as clients, can use these validators to decide whether to serve a stored response or request the resource from Pulp again.
To avoid resources being served to unauthorized parties, Pulp uses [`Cache-Control`][cache-control] directives to enforce that:
(a) cache entities always ask for validation before serving cached content;
(b) HTTP caches do not store object-storage redirects that can contain signed URLs.

A typical flow looks like:

1. A client requests a resource through a shared cache, such as a CDN.
   If the cache has no copy, it forwards the request to Pulp.
2. Pulp returns the content with `Cache-Control` requiring revalidation, `Last-Modified`, and `ETag`.
   The shared cache stores the response and its validators.
3. On a later request, the shared cache must revalidate its stored response with Pulp.
   It sends [`If-None-Match`][if-none-match] with the stored ETag, [`If-Modified-Since`][if-modified-since] with the stored date, or both.
   When both are present, Pulp checks `If-None-Match`.
4. If the content is unchanged, Pulp returns `304 Not Modified` without a body.
   The shared cache serves its stored content to the client.
   If the content changed, Pulp returns the full response with updated validators, and the cache replaces its stored copy.

### Known limitations

Pulp does not track the content that a distribution serves over time.
It infers `Last-Modified` based on the assumption that a distribution serves repository versions monotonically.
If that's not true, Pulp might tell the cache entity that a resource has not changed when it has.

The `ETag`/`If-None-Match` mechanism is unaffected by this limitation.

[cache-types]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching#types_of_caches
[last-modified]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Last-Modified
[etag]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag
[cache-control]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
[if-none-match]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match
[if-modified-since]: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-Modified-Since
