from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from pulpcore.app.domain_sync import reconcile_domains_to_alias, satellite_aliases


class Command(BaseCommand):
    """
    Reconcile the Domain table against every configured satellite database alias.

    Run this after provisioning a new satellite, after any bulk Domain changes, or
    periodically as a reconciliation job, to fix up any satellites that missed updates.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Report drift without writing any changes."),
        )
        parser.add_argument(
            "--alias",
            help=_("Only reconcile this one satellite alias, instead of every configured alias."),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if options.get("alias"):
            if options["alias"] not in satellite_aliases():
                raise CommandError(
                    _("'{alias}' is not a configured satellite alias.").format(
                        alias=options["alias"]
                    )
                )
            aliases = [options["alias"]]
        else:
            aliases = satellite_aliases()
        if not aliases:
            self.stdout.write(
                self.style.WARNING(
                    _("Only one database alias is configured; nothing to reconcile.")
                )
            )
            return

        any_drift = False
        for alias in aliases:
            self.stdout.write(_("Reconciling alias '{alias}'...").format(alias=alias))
            report = reconcile_domains_to_alias(alias, dry_run=dry_run)
            missing, extra, stale = report["missing"], report["extra"], report["stale"]

            if not (missing or extra or stale):
                self.stdout.write(_("  No drift detected."))
                continue

            any_drift = True
            if missing:
                self.stdout.write(
                    _("  {n} domain(s) missing on '{alias}': {ids}").format(
                        n=len(missing), alias=alias, ids=", ".join(str(i) for i in missing)
                    )
                )
            if extra:
                self.stdout.write(
                    _("  {n} domain(s) exist only on '{alias}' (orphaned): {ids}").format(
                        n=len(extra), alias=alias, ids=", ".join(str(i) for i in extra)
                    )
                )
            if stale:
                self.stdout.write(
                    _("  {n} domain(s) out of sync on '{alias}': {ids}").format(
                        n=len(stale), alias=alias, ids=", ".join(str(i) for i in stale)
                    )
                )

            if not dry_run:
                self.stdout.write(
                    self.style.SUCCESS(_("  Reconciled alias '{alias}'.").format(alias=alias))
                )

        if dry_run and any_drift:
            self.stdout.write(
                self.style.WARNING(_("Dry run: no changes were written. Re-run without --dry-run."))
            )
        elif not any_drift:
            self.stdout.write(self.style.SUCCESS(_("All satellite aliases are in sync.")))
