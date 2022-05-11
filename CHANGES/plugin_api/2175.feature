DeclarativeArtifact now accepts a ``urls`` option which permits multiple URLs
to be provided for a single artifact. If multiple URLs are provided, the download
stage will try each of them in turn upon encountering failures.
