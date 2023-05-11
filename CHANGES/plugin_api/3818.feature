Added support to pull-through caching for plugins with multi-artifact content types.

``Content.init_from_artifact_and_relative_path`` can now return a tuple of the new content unit
and a dict containing the mapping of that content's artifacts and their relative paths.
