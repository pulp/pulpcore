from pathlib import Path

from django.conf import settings
from django.core.checks import (
    Debug as CheckDebug,
)
from django.core.checks import (
    Error as CheckError,
)
from django.core.checks import (
    Tags,
    register,
)
from django.core.checks import (
    Warning as CheckWarning,
)
from django.db.models import Q

from pulpcore import constants


@register(deploy=True)
def content_origin_check(app_configs, **kwargs):
    messages = []
    if getattr(settings, "CONTENT_ORIGIN", "UNREACHABLE") == "UNREACHABLE":
        messages.append(
            CheckError(
                "CONTENT_ORIGIN is a required setting but it was not configured. This may be "
                "caused by invalid read permissions of the settings file. Note that "
                "CONTENT_ORIGIN is set by the installation automatically.",
                id="pulpcore.E001",
            )
        )
    return messages


@register(deploy=True)
def storage_paths(app_configs, **kwargs):
    warnings = []

    if settings.STORAGES["default"]["BACKEND"] == "pulpcore.app.models.storage.FileSystem":
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
            working_dir_dev = Path(settings.WORKING_DIRECTORY).stat().st_dev
        except OSError:
            working_dir_dev = None
            warnings.append(
                CheckWarning(
                    "Your WORKING_DIRECTORY setting points to a path that does not exist.",
                    id="pulpcore.W002",
                )
            )

        if media_root_dev and media_root_dev != working_dir_dev:
            warnings.append(
                CheckWarning(
                    "MEDIA_ROOT and WORKING_DIRECTORY are on different filesystems. "
                    "It is highly recommended that these live on the same filesystem",
                    id="pulpcore.W003",
                )
            )

    return warnings


@register(Tags.database)
def check_artifact_checksums(app_configs, **kwargs):
    from pulpcore.app.models import Artifact, RemoteArtifact

    messages = []
    allowed = set(settings.ALLOWED_CONTENT_CHECKSUMS)
    forbidden = set(constants.ALL_KNOWN_CONTENT_CHECKSUMS).difference(allowed)

    try:
        for checksum in allowed:
            if Artifact.objects.filter(**{checksum: None}).exists():
                messages.append(
                    CheckError(
                        f"There have been identified artifacts missing checksum '{checksum}'. "
                        "Run 'pulpcore-manager handle-artifact-checksums' first to populate "
                        "missing artifact checksums.",
                        id="pulpcore.E002",
                    )
                )
        for checksum in forbidden:
            if Artifact.objects.exclude(**{checksum: None}).exists():
                messages.append(
                    CheckWarning(
                        f"There have been identified artifacts with forbidden checksum "
                        f"'{checksum}'. Run 'pulpcore-manager handle-artifact-checksums' "
                        "to unset forbidden checksums.",
                        id="pulpcore.W004",
                    )
                )

        has_any_checksum = ~Q(**{c: None for c in constants.ALL_KNOWN_CONTENT_CHECKSUMS})
        missing_allowed = Q(**{c: None for c in allowed})
        if RemoteArtifact.objects.filter(has_any_checksum & missing_allowed).exists():
            messages.append(
                CheckWarning(
                    "Detected remote content without allowed checksums. "
                    "Run 'pulpcore-manager handle-artifact-checksums --report' to "
                    "view this content.",
                    id="pulpcore.W005",
                )
            )
    except Exception:
        messages.append(
            CheckDebug(
                "Skipping artifact checksum checks (table may not exist yet).",
                id="pulpcore.D001",
            )
        )

    return messages
