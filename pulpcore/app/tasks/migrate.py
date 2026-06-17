import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from gettext import gettext as _

from django.conf import settings
from django.utils.timezone import now
from rest_framework.serializers import ValidationError

from pulpcore.app.models import Artifact, ProgressReport, storage
from pulpcore.app.serializers import DomainBackendMigratorSerializer
from pulpcore.app.util import get_domain

_logger = logging.getLogger(__name__)

MIGRATION_WORKERS = getattr(settings, "MIGRATION_WORKERS", 8)
MIGRATION_BATCH_SIZE = getattr(settings, "MIGRATION_BATCH_SIZE", 500)


def _copy_artifact(old_storage, new_storage, filename):
    """Copy a single artifact between storage backends. Returns (filename, error)."""
    if new_storage.exists(filename):
        return filename, None
    try:
        file = old_storage.open(filename)
    except FileNotFoundError:
        return filename, FileNotFoundError(filename)
    try:
        new_storage.save(filename, file)
    finally:
        file.close()
    return filename, None


def _process_batch(batch, pb):
    """Wait for a batch of copy futures, increment progress, collect errors."""
    errors = []
    for future in as_completed(batch):
        filename, error = future.result()
        if error is not None:
            errors.append(filename)
        pb.increment()
    return errors


def migrate_backend(data):
    """
    Copy the artifacts from the current storage backend to a new one. Then update backend settings.

    Args:
        data (dict): validated data of the new storage backend settings
    """
    domain = get_domain()
    old_storage = domain.get_storage()
    new_storage = DomainBackendMigratorSerializer(data=data).create_storage()

    artifacts = Artifact.objects.filter(pulp_domain=domain)
    date = now()

    missing = []
    with ProgressReport(
        message=_("Migrating Artifacts"), code="migrate", total=artifacts.count()
    ) as pb:
        while True:
            batch = []
            with ThreadPoolExecutor(max_workers=MIGRATION_WORKERS) as executor:
                for digest in artifacts.values_list("sha256", flat=True):
                    filename = storage.get_artifact_path(digest)
                    future = executor.submit(
                        _copy_artifact, old_storage, new_storage, filename,
                    )
                    batch.append(future)

                    if len(batch) >= MIGRATION_BATCH_SIZE:
                        missing.extend(_process_batch(batch, pb))
                        batch = []

                if batch:
                    missing.extend(_process_batch(batch, pb))

            # Handle new artifacts saved by the content app during migration
            artifacts = Artifact.objects.filter(pulp_domain=domain, pulp_created__gte=date)
            if count := artifacts.count():
                pb.total += count
                pb.save()
                date = now()
                continue
            break

    if missing:
        raise ValidationError(
            _(
                "Found missing file(s) for {} artifact(s). Please run the repair "
                "task or delete the offending artifacts. First missing: {}"
            ).format(len(missing), missing[0])
        )

    # Update the current domain to the new storage backend settings
    msg = _("Update Domain({domain})'s Backend Settings").format(domain=domain.name)
    with ProgressReport(message=msg, code="update", total=1) as pb:
        domain.storage_class = data["storage_class"]
        domain.storage_settings = data["storage_settings"]
        domain.save(update_fields=["storage_class", "storage_settings"], skip_hooks=True)
        pb.increment()
