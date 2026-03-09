import os
import subprocess

from pathlib import Path

from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from django.apps import apps
from django.db.utils import IntegrityError

from pulpcore.app.models.content import SigningService as BaseSigningService


class Command(BaseCommand):
    """
    Django management command for adding a signing service.
    """

    help = "Adds a new SigningService."

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
        if not issubclass(SigningService, BaseSigningService):
            raise CommandError(
                _("Class '{}' is not a subclass of the base 'core:SigningService' class.").format(
                    options["class"]
                )
            )

        gpg_cmd = ["gpg"]
        if options["gnupghome"]:
            gpg_cmd += ["--homedir", options["gnupghome"]]
        if options["keyring"]:
            gpg_cmd += ["--keyring", options["keyring"]]

        result = subprocess.run(
            gpg_cmd + ["--with-colons", "--fingerprint", key_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(result.stderr.strip())

        fpr_lines = [line for line in result.stdout.splitlines() if line.startswith("fpr:")]
        if len(fpr_lines) != 1:
            raise CommandError(_("There are {} keys matching the key id.").format(len(fpr_lines)))
        fingerprint = fpr_lines[0].split(":")[9]

        result = subprocess.run(
            gpg_cmd + ["--armor", "--export", key_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(result.stderr.strip())
        public_key = result.stdout

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
