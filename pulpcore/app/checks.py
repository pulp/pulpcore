from pathlib import Path

from django.conf import settings
from django.core.checks import Warning as CheckWarning, register


@register(deploy=True)
def storage_paths(app_configs, **kwargs):
    warnings = []

    if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
        try:
            media_root_dev = Path(settings.MEDIA_ROOT).stat().st_dev
        except OSError:
            media_root_dev = None
            warnings.append(
                CheckWarning(
                    "Your MEDIA_ROOT setting points to a path that does not exist.",
                    id="pulpcore.W001",
                )
            )

        try:
            upload_temp_dir_dev = Path(settings.FILE_UPLOAD_TEMP_DIR).stat().st_dev
        except OSError:
            upload_temp_dir_dev = None
            warnings.append(
                CheckWarning(
                    "Your FILE_UPLOAD_TEMP_DIR setting points to a path that does not exist.",
                    id="pulpcore.W002",
                )
            )

        if media_root_dev and media_root_dev != upload_temp_dir_dev:
            warnings.append(
                CheckWarning(
                    "MEDIA_ROOT and FILE_UPLOAD_TEMP_DIR are on different filesystems. "
                    "It is highly recommended that these live on the same filesystem",
                    id="pulpcore.W003",
                )
            )

    return warnings
