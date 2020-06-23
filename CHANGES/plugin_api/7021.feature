Added a hook on ``Repository`` called ``artifacts_for_version()`` that plugins can override to
modify the logic behind ``RepositoryVersion.artifacts``. For now, this is used when exporting
artifacts.
