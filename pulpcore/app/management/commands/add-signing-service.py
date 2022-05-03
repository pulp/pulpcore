import os

import gnupg

from pathlib import Path

from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from django.apps import apps
from django.db.utils import IntegrityError


class Command(BaseCommand):
    """
    Django management command for adding a signing service.

    This command is in tech-preview.
    """

    help = "Adds a new AsciiArmoredDetachedSigningService. [tech-preview]"

    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            help=_("Name, the signing_service should get in the database."),
        )
        parser.add_argument(
            "script",
            help=_("Shell script where the signing service is located."),
        )
        parser.add_argument(
            "key",
            help=_("Key id of the public key."),
        )
        parser.add_argument(
            "--class",
            default="core:AsciiArmoredDetachedSigningService",
            required=False,
            help=_("Signing service class prefixed by the app label separated by a colon."),
        )
        parser.add_argument(
            "--gnupghome",
            default=os.getenv("GNUPGHOME", ""),
            required=False,
            help=_("A default GnuPG home directory to use during the initialization."),
        )
        parser.add_argument(
            "--keyring",
            required=False,
            help=_("The name of the keyring file."),
        )

    def handle(self, *args, **options):
        name = options["name"]
        script = options["script"]
        key_id = options["key"]

        if ":" not in options["class"]:
            raise CommandError(_("The signing service class was not provided in a proper format."))
        app_label, service_class = options["class"].split(":")

        try:
            SigningService = apps.get_model(app_label, service_class)
        except LookupError as e:
            raise CommandError(str(e))

        gpg = gnupg.GPG(gnupghome=options["gnupghome"], keyring=options["keyring"])

        key_list = gpg.list_keys(keys=[key_id])
        if not len(key_list) == 1:
            raise CommandError(_("There are {} keys matching the key id.").format(len(key_list)))
        fingerprint = key_list[0]["fingerprint"]
        public_key = gpg.export_keys(key_id)

        try:
            script_path = Path(script).resolve(strict=True)
        except FileNotFoundError as e:
            raise CommandError(str(e))

        try:
            SigningService.objects.create(
                name=name,
                public_key=public_key,
                pubkey_fingerprint=fingerprint,
                script=script_path,
            )
        except IntegrityError as e:
            raise CommandError(str(e))

        print(
            ("Successfully added signing service {name} for key {fingerprint}.").format(
                name=name, fingerprint=fingerprint
            )
        )
