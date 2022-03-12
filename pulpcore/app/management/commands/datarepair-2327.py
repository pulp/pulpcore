from gettext import gettext as _

from django.db import connection
from django.conf import settings
from django.core.management import BaseCommand
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str

import cryptography

from pulpcore.app.models import Remote


class Command(BaseCommand):
    """
    Django management command for repairing incorrectly migrated remote data.
    """

    help = _(
        "Repairs issue #2327. A small number of configuration settings may have been "
        "corrupted during an upgrade from a previous version of Pulp to a Pulp version "
        "between 3.15-3.18, resulting in trouble when syncing or viewing certain remotes. "
        "This script repairs the data (which was not lost)."
    )

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Don't modify anything, just collect results on how many Remotes are impacted."),
        )

    def handle(self, *args, **options):

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

        for remote_pk in Remote.objects.filter(possibly_affected_remotes).values_list(
            "pk", flat=True
        ):
            try:
                remote = Remote.objects.get(pk=remote_pk)
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
                    Remote.objects.filter(pk=remote_pk).update(**field_values)
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
