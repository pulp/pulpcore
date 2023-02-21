from django.apps import apps
from django.core.management import BaseCommand, CommandError
from django.db.utils import IntegrityError

import argparse
import json
import os

from gettext import gettext as _
from pathlib import Path
from voluptuous import Optional, Required, Schema

from pulp_ansible.app.models import SigstoreSigningService

SIGSTORE_GLOBAL_OPTIONS_SCHEMA = Schema(
    {
        Required("signing-service-name"): str,
        Optional("rekor-url"): str,
        Optional("rekor-root-pubkey"): str,
        Optional("oidc-issuer"): str,
    }
)
SIGSTORE_SIGN_SCHEMA = Schema(
    {
        Optional("fulcio-url"): str,
        Required("identity-token"): str,
        Optional("oidc-client-id"): str,
        Optional("oidc-client-secret"): str,
        Optional("sigstore-bundle"): bool,
        Optional("ctfe"): str,
    }
)
SIGSTORE_VERIFY_SCHEMA = Schema(
    {
        Optional("verify-offline"): bool,
        Required("cert-identity"): str,
    }
)

SIGSTORE_CONFIGURATION_FILE_SCHEMA = Schema(
    {
        Required("global-options"): SIGSTORE_GLOBAL_OPTIONS_SCHEMA,
        Required("sign-options"): SIGSTORE_SIGN_SCHEMA,
        Required("verify-options"): SIGSTORE_VERIFY_SCHEMA,
    }
)

# Taken from https://github.com/sigstore/sigstore-python/blob/55f98f663721be34a5e5b63fb72e740c3d580f66/sigstore/_cli.py#L64
def _to_bool(val):
    if isinstance(val, bool):
        return val
    val = val.lower()
    if val in {"y", "yes", "true", "t", "on", "1"}:
        return True
    elif val in {"n", "no", "false", "f", "off", "0"}:
        return False
    else:
        raise ValueError(f"can't coerce '{val}' to a boolean")


class Command(BaseCommand):
    """
    Django management command for adding a Sigstore signing service.

    This command is in tech preview.
    """

    help = "Adds a new Sigstore signing service. [tech-preview]"

    def add_arguments(self, parser):
        global_options = parser.add_argument_group("Global Sigstore options")
        global_options.add_argument(
            "--from-file",
            help=_("Load the Sigstore configuration from a JSON file. File configuration can be overriden by specified arguments.\n"),
        )
        global_options.add_argument(
            "--signing-service-name",
            type=str,
            metavar="NAME",
            help=_("Name for registering the Sigstore signing service.\n"),
        )
        global_options.add_argument(
            "--rekor-url",
            metavar="URL",
            type=str,
            default="https://rekor.sigstore.dev",
            help=_("The Rekor instance to use. WARNING: defaults to the public good Sigstore instance https://rekor.sigstore.dev"),
        )
        global_options.add_argument(
            "--rekor-root-pubkey",
            metavar="FILE",
            type=argparse.FileType("rb"),
            help=_("A PEM-encoded root public key for Rekor itself"),
            default=None,
        )
        global_options.add_argument(
            "--oidc-issuer",
            metavar="URL",
            type=str,
            default="https://oauth2.sigstore.dev",
            help=_("The OpenID Connect issuer to use to sign and verify the artifact"),
        )

        sign_options = parser.add_argument_group("Sign options")
        sign_options.add_argument(
            "--oidc-client-id",
            metavar="ID",
            type=str,
            default=os.getenv("SIGSTORE_OIDC_CLIENT_ID", "sigstore"),
            help=_("The custom OpenID Connect client ID to use during OAuth2"),
        )
        sign_options.add_argument(
            "--oidc-client-secret",
            metavar="SECRET",
            type=str,
            default=os.getenv("SIGSTORE_OIDC_CLIENT_SECRET"),
            help=_("The custom OpenID Connect client secret to use during OAuth2"),
        )
        sign_options.add_argument(
            "--sigstore-bundle",
            metavar="BOOL",
            type=bool,
            help=_("Write a single Sigstore bundle file to the collection."),
        )
        sign_options.add_argument(
            "--fulcio-url",
            metavar="URL",
            type=str,
            default="https://fulcio.sigstore.dev",
            help=_("The Fulcio instance to use. WARNING: defaults to the public good Sigstore instance https://fulcio.sigstore.dev"),
        )
        sign_options.add_argument(
            "--identity-token",
            metavar="URL",
            type=str,
            help=_("Environment variable name for an OIDC identity token present on the server."),
        )
        sign_options.add_argument(
            "--ctfe",
            metavar="FILE",
            type=argparse.FileType("rb"),
            help=_("A PEM-encoded public key for the CT log"),
        )

        verify_options = parser.add_argument_group("Verify options")
        verify_options.add_argument(
            "--cert-oidc-issuer",
            metavar="URL",
            type=str,
            default=os.getenv("SIGSTORE_CERT_OIDC_ISSUER"),
            help=_("The OIDC issuer URL to check for in the certificate's OIDC issuer extension"),
        )
        verify_options.add_argument(
            "--cert-identity",
            metavar="IDENTITY",
            type=str,
            default=os.getenv("SIGSTORE_CERT_IDENTITY"),
            help=_("The identity to check for in the certificate's Subject Alternative Name"),
        )
        verify_options.add_argument(
            "--verify-offline",
            metavar="BOOL",
            type=bool,
            help=_("Perform offline signature verification. Requires a Sigstore bundle as a verification input.")
        )

    def handle(self, *args, **options):
        if "from_file" in options:
            file_path = Path(options["from_file"])

            with open(file_path, "r") as file:
                sigstore_config = json.load(file)
                SIGSTORE_CONFIGURATION_FILE_SCHEMA(sigstore_config)
                global_sigstore_options, sign_options, verify_options = sigstore_config["global-options"], sigstore_config["sign-options"], sigstore_config["verify-options"]
                options = {option_name.replace("_", "-") : option_value for option_name, option_value in options.items()}
                for option_name, option_value in options.items():
                    if option_value:
                        if option_name in global_sigstore_options:
                            global_sigstore_options[option_name] = option_value
                        elif option_name in sign_options:
                            sign_options[option_name] = option_value
                        elif option_name in verify_options:
                            verify_options[option_name] = option_value

                verify_offline = _to_bool(verify_options["verify-offline"])
                sigstore_bundle = _to_bool(sign_options["sigstore-bundle"])
                if verify_offline and not sigstore_bundle:
                    raise Exception("Cannot perform offline verification if Sigstore signing service is not configured to write Sigstore bundles.")

                try:
                    SigstoreSigningService.objects.create(
                        name=global_sigstore_options["signing-service-name"],
                        rekor_url=global_sigstore_options["rekor-url"],
                        rekor_root_pubkey=global_sigstore_options.get("rekor-root-pubkey"),
                        oidc_issuer=global_sigstore_options.get("oidc-issuer"),
                        fulcio_url=sign_options["fulcio-url"],
                        identity_token=sign_options["identity-token"],
                        oidc_client_id=sign_options.get("oidc-client-id"),
                        oidc_client_secret=sign_options.get("oidc-client-secret"),
                        sigstore_bundle=sigstore_bundle,
                        ctfe=sign_options.get("ctfe"),
                        cert_identity=verify_options["cert-identity"],
                        verify_offline=verify_offline,
                    )  

                    print(
                        f"Successfully configured the Sigstore signing service {global_sigstore_options['signing-service-name']} with the following parameters: \n"
                        f"Rekor instance URL: {global_sigstore_options['rekor-url']}\n"
                        f"Rekor root public key: {global_sigstore_options.get('rekor-root-pubkey')}\n"
                        f"Fulcio instance URL: {sign_options['fulcio-url']}\n"
                        f"OIDC issuer: {global_sigstore_options.get('oidc-issuer')}\n"
                        f"OIDC ID token environment variable: {sign_options['identity-token']}\n"
                        f"OIDC client ID environment variable: {sign_options.get('oidc-client-id')}\n"
                        f"OIDC client secret environment variable: {sign_options.get('oidc-client-secret')}\n"
                        f"Output Rekor bundle: {sigstore_bundle}\n"
                        f"Require offline verification: {verify_offline}\n"
                        f"Certificate Transparency log public key: {sign_options.get('ctfe')}\n"
                        f"OIDC identity of the signer: {verify_options['cert-identity']}\n"
                    )

                except IntegrityError as e:
                    raise CommandError(str(e))
