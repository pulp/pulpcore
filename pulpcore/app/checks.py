import sys
from gettext import gettext as _
from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Warning as CheckWarning, register
from django.db import connection

from pulpcore import constants
from pulpcore.app.models import Artifact


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


@register()
def content_origin_check(app_configs, **kwargs):
    errors = []

    try:
        settings.CONTENT_ORIGIN
    except AttributeError:
        errors.append(
            Error(
                _(
                    "CONTENT_ORIGIN is a required setting but it was not configured. This may be "
                    "caused by invalid read permissions of the settings file. Note that "
                    "CONTENT_ORIGIN is set by the installer automatically."
                ),
                id="pulpcore.E001",
            )
        )

    return errors


@register()
def checksum_setting_check(app_configs, **kwargs):
    errors = []
    unknown_checksums = set(settings.ALLOWED_CONTENT_CHECKSUMS).difference(
        constants.ALL_KNOWN_CONTENT_CHECKSUMS
    )

    if "sha256" not in settings.ALLOWED_CONTENT_CHECKSUMS:
        errors.append(
            Error(
                _(
                    "ALLOWED_CONTENT_CHECKSUMS MUST contain 'sha256' - Pulp's "
                    " content-storage-addressing relies on sha256 to identify entities.",
                ),
                id="pulpcore.E002",
            )
        )

    if unknown_checksums:
        errors.append(
            Error(
                _(
                    "ALLOWED_CONTENT_CHECKSUMS may only contain algorithms known to pulp - see "
                    "constants.ALL_KNOWN_CONTENT_CHECKSUMS for the allowed list. Unknown algorithms"
                    " provided: {}".format(unknown_checksums)
                ),
                id="pulpcore.E003",
            )
        )

    return errors


@register()
def artifact_checksum_check(app_configs, **kwargs):
    errors = []
    forbidden_checksums = set(constants.ALL_KNOWN_CONTENT_CHECKSUMS).difference(
        settings.ALLOWED_CONTENT_CHECKSUMS
    )
    unknown_checksums = set(settings.ALLOWED_CONTENT_CHECKSUMS).difference(
        constants.ALL_KNOWN_CONTENT_CHECKSUMS
    )

    if len(sys.argv) >= 2 and sys.argv[1] == "handle-artifact-checksums":
        # user is running handle-artifact-checksums command
        return errors

    if Artifact._meta.db_table not in connection.introspection.table_names():
        # artifact table doesn't exist (ie database hasn't been migrated)
        connection.close()
        return errors

    for checksum in settings.ALLOWED_CONTENT_CHECKSUMS:
        if checksum in unknown_checksums:
            # the E003 check will handle this. skip checksum to prevent FieldError.
            continue

        if Artifact.objects.filter(**{checksum: None}).exists():
            errors.append(
                Error(
                    _(
                        "There have been identified artifacts missing checksum '{}'. "
                        "Run 'pulpcore-manager handle-artifact-checksums' first to populate "
                        "missing artifact checksums."
                    ).format(checksum),
                    id="pulpcore.E004",
                )
            )

    for checksum in forbidden_checksums:
        if Artifact.objects.exclude(**{checksum: None}).exists():
            errors.append(
                Error(
                    _(
                        "There have been identified artifacts with forbidden checksum '{}'. "
                        "Run 'pulpcore-manager handle-artifact-checksums' first to unset "
                        "forbidden checksums."
                    ).format(checksum),
                    id="pulpcore.E005",
                )
            )

    return errors
