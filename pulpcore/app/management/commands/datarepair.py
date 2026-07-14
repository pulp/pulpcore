from gettext import gettext as _

import cryptography
from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import connections
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str

from pulpcore.app import models
from pulpcore.app.util import domain_db, for_each_domain


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
        elif issue == "7465":
            self.repair_7465(options)
        else:
            raise CommandError(_("Unknown issue: '{}'").format(issue))

    def repair_7272(self, options):
        dry_run = options["dry_run"]

        number_broken = 0
        self.stdout.write()

        # KI-08: iterate every domain via `domain_db()` (Layer 3) rather than a bare
        # `Domain.objects.all()` loop -- without it, every query below would resolve through the
        # router's default fallback (`"default"`) regardless of which domain is being processed,
        # silently seeing/fixing nothing for a domain hosted on a satellite. `.using(alias)` is
        # applied explicitly on every direct queryset here per the Layer 3 convention;
        # `rv._content_relationships()` (a `RepositoryContent` queryset built deep inside the
        # model) is left unqualified since it correctly picks up the ContextVar `domain_db()` set.
        for domain in models.Domain.objects.all():
            has_printed_domain = False
            with domain_db(domain) as alias:
                for repo in models.Repository.objects.using(alias).filter(pulp_domain=domain):
                    for rv in models.RepositoryVersion.objects.using(alias).filter(repository=repo):
                        needs_fix = False
                        if rv.content_ids is not None:
                            cached_id_set = set(rv.content_ids)
                            repositorycontent_id_set = set(
                                rv._content_relationships().values_list("content__pk", flat=True)
                            )
                            if cached_id_set != repositorycontent_id_set:
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
                        rv_count_details = models.RepositoryVersionContentDetails.objects.using(
                            alias
                        ).filter(
                            repository_version=rv,
                            count_type=models.RepositoryVersionContentDetails.PRESENT,
                        )

                        # need to sum across all content types
                        total_count = sum(rvcd.count for rvcd in rv_count_details)

                        if total_count != repositorycontent_id_count:
                            needs_fix = True
                            if not has_printed_domain:
                                self.stdout.write(f'In domain "{domain.name}"')
                                has_printed_domain = True
                            self.stdout.write(
                                f'\tRepository "{repo.name}" (type "{repo.pulp_type}") '
                                f"version {rv.number} has a mismatch between the "
                                "RepositoryContent and RepositoryVersionContentDetails"
                            )

                        if needs_fix:
                            number_broken += 1

                            if not dry_run:
                                rv.content_ids = list(
                                    rv._content_relationships().values_list(
                                        "content__pk", flat=True
                                    )
                                )
                                rv.save()
                                rv._compute_counts()

            self.stdout.write()

        if not number_broken:
            self.stdout.write("Finished. (OK)")
        else:
            if dry_run:
                self.stdout.write(
                    f"Finished. (dry run: {number_broken} incorrect repository versions "
                    f"- no changes)"
                )
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

        counts = {"number_unencrypted": 0, "number_multi_encrypted": 0}

        # KI-08: `Remote` is data-plane, so a bare `Remote.objects.filter(...)` (the original
        # shape of this method, and the design doc's own listed example of this bug) only ever
        # sees `default`'s remotes. `for_each_domain()` (Layer 3) re-runs the whole sweep once
        # per domain with `.using(alias)`/the raw-SQL fallback pinned to that domain's own alias.
        def _repair_2327_for_domain(domain, alias):
            for remote_pk in (
                models.Remote.objects.using(alias)
                .filter(possibly_affected_remotes)
                .values_list("pk", flat=True)
            ):
                try:
                    remote = models.Remote.objects.using(alias).get(pk=remote_pk)
                    # if we can get the remote successfully, it is either OK or the fields are
                    # encrypted more than once
                except cryptography.fernet.InvalidToken:
                    # If decryption fails then it probably hasn't been encrypted yet
                    # get the raw column value, avoiding any Django field handling
                    with connections[alias].cursor() as cursor:
                        cursor.execute(
                            "SELECT username, password, proxy_username, proxy_password, "
                            "client_key FROM core_remote WHERE pulp_id = %s",
                            [str(remote_pk)],
                        )
                        row = cursor.fetchone()

                    field_values = {}

                    for field, value in zip(fields, row):
                        field_values[field] = value

                    if not dry_run:
                        models.Remote.objects.using(alias).filter(pk=remote_pk).update(
                            **field_values
                        )
                    counts["number_unencrypted"] += 1
                else:
                    times_decrypted = 0
                    keep_trying = True
                    needs_update = False

                    while keep_trying:
                        for field in fields:
                            # value gets decrypted once on access
                            field_value = getattr(remote, field)
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
                        counts["number_multi_encrypted"] += 1

        for_each_domain(_repair_2327_for_domain)
        number_unencrypted = counts["number_unencrypted"]
        number_multi_encrypted = counts["number_multi_encrypted"]

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

    def repair_7465(self, options):
        dry_run = options["dry_run"]

        number_missing = 0
        self.stdout.write()

        # KI-08: see repair_7272's comment above -- same `domain_db()`/`.using(alias)` fix.
        for domain in models.Domain.objects.all():
            has_printed_domain = False
            with domain_db(domain) as alias:
                for repo in models.Repository.objects.using(alias).filter(pulp_domain=domain):
                    for rv in models.RepositoryVersion.objects.using(alias).filter(repository=repo):
                        if rv.content_ids is None:
                            if not has_printed_domain:
                                self.stdout.write(f'In domain "{domain.name}"')
                                has_printed_domain = True
                            number_missing += 1
                            self.stdout.write(
                                f'\tRepository "{repo.name}" (type "{repo.pulp_type}") '
                                f"version {rv.number} has a missing content_ids cache"
                            )
                            if not dry_run:
                                rv.content_ids = list(
                                    rv._content_relationships().values_list(
                                        "content__pk", flat=True
                                    )
                                )
                                rv.save()

        if not number_missing:
            self.stdout.write("Finished. (OK)")
        else:
            if dry_run:
                self.stdout.write(
                    f"Finished. (dry run: {number_missing} repository versions need fixing)"
                )
            else:
                self.stdout.write(f"Finished. ({number_missing} repository versions fixed)")
