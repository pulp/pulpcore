from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from django.core.exceptions import ObjectDoesNotExist

from django.apps import apps
from django.db.utils import IntegrityError

from pulp_ansible.app.models import SigstoreSigningService

class Command(BaseCommand):
    """
    Django management command for removing a Sigstore signing service.

    This command is in tech-preview.
    """

    help = "Removes an existing SigstoreSigningService. [tech-preview]"

    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            help=_("Name that the sigstore_signing_service has in the database."),
        )

    def handle(self, *args, **options):
        name = options["name"]

        try:
            SigstoreSigningService.objects.get(name=name).delete()
        except IntegrityError:
            raise CommandError(
                _("Sigstore Signing service '{}' could not be removed because it's still in use.").format(
                    name
                )
            )
        except ObjectDoesNotExist:
            raise CommandError(
                _("Sigstore Signing service '{}' does not exists.").format(name)
            )
        else:
            self.stdout.write(_("Sigstore Signing service '{}' has been successfully removed.").format(name))
