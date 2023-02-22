from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from django.core.exceptions import ObjectDoesNotExist

from django.apps import apps
from django.db.utils import IntegrityError

from pulpcore.app.models.content import SigningService as BaseSigningService


class Command(BaseCommand):
    """
    Django management command for removing a signing service.
    """

    help = "Removes an existing SigningService."

    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            help=_("Name that the signing_service has in the database."),
        )
        parser.add_argument(
            "--class",
            default="core:AsciiArmoredDetachedSigningService",
            required=False,
            help=_("Signing service class prefixed by the app label separated by a colon."),
        )

    def handle(self, *args, **options):
        name = options["name"]
        if ":" not in options["class"]:
            raise CommandError(_("The signing service class was not provided in a proper format."))
        app_label, service_class = options["class"].split(":")

        try:
            SigningService = apps.get_model(app_label, service_class)
        except LookupError as e:
            raise CommandError(str(e))
        if not issubclass(SigningService, BaseSigningService):
            raise CommandError(
                _("Class '{}' is not a subclass of the base 'core:SigningService' class.").format(
                    options["class"]
                )
            )

        try:
            SigningService.objects.get(name=name).delete()
        except IntegrityError:
            raise CommandError(
                _("Signing service '{}' could not be removed because it's still in use.").format(
                    name
                )
            )
        except ObjectDoesNotExist:
            raise CommandError(
                _("Signing service '{}' of class '{}' does not exists.").format(
                    name, options["class"]
                )
            )
        else:
            self.stdout.write(_("Signing service '{}' has been successfully removed.").format(name))
