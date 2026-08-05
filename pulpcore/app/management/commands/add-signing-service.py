import os
import subprocess
import warnings
from gettext import gettext as _
from pathlib import Path

from django.apps import apps
from django.core.management import BaseCommand, CommandError
from django.db.utils import IntegrityError

from pulpcore.app.models.content import SigningService as BaseSigningService

ENV_DEFAULTS = {
    "gpg": "GNUPGHOME",
    "sq": "SEQUOIA_HOME",
}


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
            help=_("Key id or fingerprint of the public key."),
        )
        parser.add_argument(
            "--class",
            default="core:AsciiArmoredDetachedSigningService",
            required=False,
            help=_("Signing service class prefixed by the app label separated by a colon."),
        )
        parser.add_argument(
            "--backend",
            choices=["gpg", "sq"],
            default="gpg",
            required=False,
            help=_("Key management backend to use for extracting key metadata. (default: gpg)"),
        )
        parser.add_argument(
            "--home",
            default=None,
            required=False,
            help=_(
                "Home directory for the key management backend. "
                "Defaults to $GNUPGHOME (gpg) or $SEQUOIA_HOME (sq)."
            ),
        )
        parser.add_argument(
            "--gnupghome",
            default=None,
            required=False,
            help=_("Deprecated: use --home instead."),
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

        backend = options["backend"]

        if options["home"] and options["gnupghome"]:
            raise CommandError(_("--home and --gnupghome are mutually exclusive."))

        if options["gnupghome"]:
            warnings.warn(
                "--gnupghome is deprecated; use --home instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        home = options["home"] or options["gnupghome"] or os.getenv(ENV_DEFAULTS[backend], "")

        if backend == "sq":
            fingerprint, public_key = self._extract_key_from_sq(
                key_id, home, options.get("keyring")
            )
        else:
            fingerprint, public_key = self._extract_key_from_gpg(
                key_id, home, options.get("keyring")
            )

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

    def _extract_key_from_gpg(self, key_id, home, keyring):
        gpg_cmd = ["gpg"]
        if home:
            gpg_cmd += ["--homedir", home]
        if keyring:
            gpg_cmd += ["--keyring", keyring]

        result = subprocess.run(
            gpg_cmd + ["--with-colons", "--fingerprint", key_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(result.stderr.strip())

        lines = result.stdout.splitlines()

        # Count actual keys (pub:/sec: lines), not fingerprint lines. GPG emits
        # a separate fpr: line for the primary key and each subkey, so a single
        # key with subkeys produces multiple fpr: lines.
        key_lines = [l for l in lines if l.startswith(("pub:", "sec:"))]  # noqa: E741
        if len(key_lines) != 1:
            raise CommandError(_("There are {} keys matching the key id.").format(len(key_lines)))

        # Use the primary key fingerprint (first fpr: line in GPG's output).
        fingerprint = [l.split(":")[9] for l in lines if l.startswith("fpr:")][0]  # noqa: E741

        result = subprocess.run(
            gpg_cmd + ["--armor", "--export", key_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(result.stderr.strip())
        public_key = result.stdout

        return fingerprint, public_key

    def _extract_key_from_sq(self, key_id, home, keyring):
        from pysequoia import Cert

        sq_cmd = ["sq"]
        if home:
            sq_cmd += ["--home", home]
        if keyring:
            sq_cmd += ["--keyring", keyring]

        result = subprocess.run(
            sq_cmd + ["cert", "export", "--cert", key_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise CommandError(result.stderr.strip())
        public_key = result.stdout

        try:
            cert = Cert.from_bytes(public_key.encode("utf-8"))
        except Exception as e:
            raise CommandError(
                _("Failed to parse exported certificate for '{}': {}").format(key_id, e)
            )

        fingerprint = cert.fingerprint.upper()

        return fingerprint, public_key
