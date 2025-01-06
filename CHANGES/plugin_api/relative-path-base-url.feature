Modified the `artifact_url` method from `ArtifactDistribution` model to return a relative URL
(no protocol, fqdn, and port) in case `CONTENT_ORIGIN` is not defined.
