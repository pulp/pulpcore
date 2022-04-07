from gettext import gettext as _

from django.db import connection
from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str

import cryptography

from pulpcore.app import models


class Command(BaseCommand):
    """
    Django management command for repairing improper data mistakes and migrations.
    """

    help = _("Repairs various data corruption issues known to Pulp.")

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument("issue", help=_("The github issue # of the issue to be fixed."))
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_(
                "Don't modify anything, just show the results of what would happen if this "
                "command were run."
            ),
        )

    def handle(self, *args, **options):
        """Implement the command."""
        issue = options["issue"]

        if issue == "2327":
            self.repair_2327(options)
        elif issue == "7272":
            self.repair_7272(options)
        else:
            raise CommandError(_("Unknown issue: '{}'").format(issue))

    def repair_7272(self, options):
        dry_run = options["dry_run"]

        number_broken = 0
        self.stdout.write()

        for domain in models.Domain.objects.all():
            has_printed_domain = False
            for repo in models.Repository.objects.filter(pulp_domain=domain):
                for rv in models.RepositoryVersion.objects.filter(repository=repo):
                    needs_fix = False
                    if rv.content_ids is not None:
                        cached_id_set = set(rv.content_ids)
                        repositorycontent_id_set = set(
                            rv._content_relationships().values_list("content__pk", flat=True)
                        )
                        if cached_id_set != repositorycontent_id_set:
                            number_broken += 1
                            if not has_printed_domain:
                                self.stdout.write(f'In domain "{domain.name}"')
                                has_printed_domain = True

                            self.stdout.write(
                                f'\tRepository "{repo.name}" (type "{repo.pulp_type}") '
                                f"version {rv.number} has a mismatch between the "
                                "RepositoryContent and the cached ID set"
                            )
                            needs_fix = True

                    repositorycontent_id_count = rv._content_relationships().count()
                    if repositorycontent_id_count == 0:
                        continue
                    rv_count_details = models.RepositoryVersionContentDetails.objects.get(
                        repository_version=rv,
                        count_type=models.RepositoryVersionContentDetails.PRESENT,
                    )

                    if rv_count_details.count != repositorycontent_id_count:
                        if not has_printed_domain:
                            self.stdout.write(f'In domain "{domain.name}"')
                            has_printed_domain = True
                        self.stdout.write(
                            f'\tRepository "{repo.name}" (type "{repo.pulp_type}") '
                            f"version {rv.number} has a mismatch between the "
                            "RepositoryContent and RepositoryVersionContentDetails"
                        )

                    if needs_fix and not dry_run:
                        rv.content_ids = list(
                            rv._content_relationships().values_list("content__pk", flat=True)
                        )
                        rv.save()
                        rv._compute_counts()

            self.stdout.write()

        if not number_broken:
            self.stdout.write("Finished. (OK)")
        else:
            if dry_run:
                self.stdout.write("Finished. (no changes)")
            else:
                self.stdout.write(f"Finished. ({number_broken} repository versions fixed)")

    def repair_2327(self, options):
        dry_run = options["dry_run"]
        fields = ("username", "password", "proxy_username", "proxy_password", "client_key")

        with open(settings.DB_ENCRYPTION_KEY, "rb") as key_file:
            fernet = cryptography.fernet.Fernet(key_file.read())

        possibly_affected_remotes = (
            Q(username__isnull=False)
            | Q(password__isnull=False)
            | Q(proxy_username__isnull=False)
            | Q(proxy_password__isnull=False)
            | Q(client_key__isnull=False)
        )

        number_unencrypted = 0
        number_multi_encrypted = 0

        for remote_pk in models.Remote.objects.filter(possibly_affected_remotes).values_list(
            "pk", flat=True
        ):
            try:
                remote = models.Remote.objects.get(pk=remote_pk)
                # if we can get the remote successfully, it is either OK or the fields are
                # encrypted more than once
            except cryptography.fernet.InvalidToken:
                # If decryption fails then it probably hasn't been encrypted yet
                # get the raw column value, avoiding any Django field handling
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT username, password, proxy_username, proxy_password, client_key "
                        "FROM core_remote WHERE pulp_id = %s",
                        [str(remote_pk)],
                    )
                    row = cursor.fetchone()

                field_values = {}

                for field, value in zip(fields, row):
                    field_values[field] = value

                if not dry_run:
                    models.Remote.objects.filter(pk=remote_pk).update(**field_values)
                number_unencrypted += 1
            else:
                times_decrypted = 0
                keep_trying = True
                needs_update = False

                while keep_trying:
                    for field in fields:
                        field_value = getattr(remote, field)  # value gets decrypted once on access
                        if not field_value:
                            continue

                        try:
                            # try to decrypt it again
                            field_value = force_str(fernet.decrypt(force_bytes(field_value)))
                            # it was decrypted successfully again time, so it was probably
                            # encrypted multiple times over. lets re-set the value with the
                            # newly decrypted value
                            setattr(remote, field, field_value)
                            needs_update = True
                        except cryptography.fernet.InvalidToken:
                            # couldn't be decrypted again, stop here
                            keep_trying = False

                    times_decrypted += 1

                if needs_update:
                    if not dry_run:
                        remote.save()
                    number_multi_encrypted += 1

        if dry_run:
            print("Remotes with un-encrypted fields: {}".format(number_unencrypted))
            print("Remotes encrypted multiple times: {}".format(number_multi_encrypted))
        else:
            if not number_unencrypted and not number_multi_encrypted:
                print("Finished. (OK)")
            else:
                print(
                    "Finished. ({} remotes fixed)".format(
                        number_unencrypted + number_multi_encrypted
                    )
                )
