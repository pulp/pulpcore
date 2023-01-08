from django.apps import apps
from django.core.management import BaseCommand, CommandError
from django.db.utils import IntegrityError

# import SigstoreSigningService model 
from sigstore.oidc import detect_credential

class Command(BaseCommand):
    """
    Django management command for adding a Sigstore signing service.

    This command is in tech preview.
    """

    help = "Adds a new Sigstore signing service. [tech-preview]"

    def add_arguments(self, parser):
        parser.add_arguments(
            "name",
            help=_("Name for registering the Sigstore signing service."),
        )
        parser.add_argument(
            "--sigstore-rekor-instance",
            default="https://rekor.sigstore.dev",
            required=False,
            help=_("Instance of Rekor used to store Sigstore signature logs. If not set, defaults to the Rekor public good instance https://rekor.sigstore.dev"),
        )
        parser.add_argument(
            "--sigstore-fulcio-instance",
            default="https://fulcio.sigstore.dev",
            required=False,
            help=_("Instance of Fulcio used to generate Sigstore signing certificates. If not set, defaults to the Fulcio public good instance https://fulcio.sigstore.dev"),
        )
        # TODO: Add OIDC server option 
        parser.add_argument(
            "--sigstore-oidc-identifier",
            required=True,
            help=_("The identifier (for example, email) used by Sigstore to sign artifacts."),
        )
        parser.add_argument(
            "--sigstore-oidc-client-id",
            required=True,
            help=_("The OIDC client ID environment variable present on the server to authenticate to Sigstore.")
        )
        parser.add_argument(
            "--sigstore-oidc-client-secret",
            required=True,
            help=_("The OIDC client secret environment variable present on the server to authenticate to Sigstore.")
        )
    def handle(self, *args, **options):
        name = options["name"]
        sigstore_rekor_instance = options["sigstore-rekor-instance"]
        if sigstore_rekor_instance == "https://rekor.sigstore.dev":
            print("Warning: Sigstore Rekor instance set to default public instance 'https://rekor.sigstore.dev')
        sigstore_fulcio_instance = options["sigstore-fulcio-instance"]
        if sigstore_fulcio_instance == "https://fulcio.sigstore.dev":
            print("Warning: Sigstore Fulcio instance set to default public instance 'https://fulcio.sigstore.dev')
        sigstore_oidc_identifier = options["sigstore-oidc-identifier"]
        sigstore_oidc_client_id = options["sigstore-oidc-client-id"]
        sigstore_oidc_client_secret = options["sigstore-oidc-client-secret"]

        # TODO: Perform a lookup and validation of OIDC credentials on the Pulp server with `detect_credential`

        try:
            apps.get_model("SigstoreSigningService")
        except LookupError as e:
            raise CommandError(str(e))

        # TODO: Eventually validate OIDC identifier provided (if a DB of authorized signers exists)

        try:
            SigstoreSigningService.objects.create(
                name=name,
                sigstore_rekor_instance=sigstore_rekor_instance,
                sigstore_fulcio_instance=sigstore_fulcio_instance,
                sigstore_oidc_identifier=sigstore_oidc_identifier,
                sigstore_oidc_client_id=sigstore_oidc_client_id,
                sigstore_oidc_client_secret=sigstore_oidc_client_secret,
            )

        except IntegrityError as e:
            raise CommandError(str(e))

        print(
            (
                f"Successfully added Sigstore signing service {name} for signer {sigstore_oidc_identifier} with the following configuration: \n"
                f"Rekor instance: {sigstore_rekor_instance}\n"
                f"Fulcio instance: {sigstore_fulcio_instance}\n"
                f"Signer OIDC identifier: {sigstore_oidc_identifier}\n"
                f"OIDC client ID environment variable: {sigstore_oidc_client_id}\n"
                f"OIDC client secret environment variable: {sigstore_oidc_client_secret}\n" 
            )
        )

