import logging
from gettext import gettext as _

from django.utils.timezone import now
from rest_framework.serializers import ValidationError
from pulpcore.app.models import Artifact, Domain, storage, ProgressReport
from pulpcore.app.serializers import DomainBackendMigratorSerializer
from pulpcore.app.util import get_domain
from pulpcore.constants import TASK_STATES

_logger = logging.getLogger(__name__)


def migrate_backend(data):
    """
    Copy the artifacts from the current storage backend to a new one. Then update backend settings.

    Args:
        data (str): encrypted json string of the new storage backend settings
    """
    data = DomainBackendMigratorSerializer.decrypt_data(data)
    domain = get_domain()
    old_storage = domain.get_storage()
    new_storage = Domain(**data).get_storage()

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
        # Special handling for default domain
        if domain.name == "default":
            msg = _(
                "PLEASE UPDATE CONFIG FILE WITH THE NEW STORAGE SETTINGS BEFORE NEXT DB MIGRATION!"
            )
            _logger.warning(msg)
            ProgressReport(message=msg, code="URGENT", state=TASK_STATES.SKIPPED).save()

        domain.storage_class = data["storage_class"]
        domain.storage_settings = data["storage_settings"]
        domain.save(update_fields=["storage_class", "storage_settings"])
        pb.increment()
