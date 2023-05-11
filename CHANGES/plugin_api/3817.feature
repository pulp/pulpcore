Added support to pull-through caching for streaming metadata files.

``Remote.get_remote_artifact_content_type`` can now return ``None`` to inform the content app that
the requested path is a metadata file that should be streamed and not saved for the pull-through
caching feature.
