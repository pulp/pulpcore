import logging
from gettext import gettext as _

from django.utils.timezone import now
from rest_framework.serializers import ValidationError
from pulpcore.app.models import Artifact, storage, ProgressReport
from pulpcore.app.serializers import DomainBackendMigratorSerializer
from pulpcore.app.util import get_domain

_logger = logging.getLogger(__name__)


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

    with ProgressReport(
        message=_("Migrating Artifacts"), code="migrate", total=artifacts.count()
    ) as pb:
        while True:
            for digest in pb.iter(artifacts.values_list("sha256", flat=True)):
                filename = storage.get_artifact_path(digest)
                if not new_storage.exists(filename):
                    try:
                        file = old_storage.open(filename)
                    except FileNotFoundError:
                        raise ValidationError(
                            _(
                                "Found missing file for artifact(sha256={}). Please run the repair "
                                "task or delete the offending artifact."
                            ).format(digest)
                        )
                    new_storage.save(filename, file)
                    file.close()
            # Handle new artifacts saved by the content app
            artifacts = Artifact.objects.filter(pulp_domain=domain, pulp_created__gte=date)
            if count := artifacts.count():
                pb.total += count
                pb.save()
                date = now()
                continue
            break

    # Update the current domain to the new storage backend settings
    msg = _("Update Domain({domain})'s Backend Settings").format(domain=domain.name)
    with ProgressReport(message=msg, code="update", total=1) as pb:
        domain.storage_class = data["storage_class"]
        domain.storage_settings = data["storage_settings"]
        domain.save(update_fields=["storage_class", "storage_settings"], skip_hooks=True)
        pb.increment()
