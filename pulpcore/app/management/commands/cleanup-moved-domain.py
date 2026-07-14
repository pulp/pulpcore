from gettext import gettext as _

from django.core.management import BaseCommand, CommandError
from django.utils.timezone import now

from pulpcore.app.domain_move import DomainMoveError, delete_domain_data
from pulpcore.app.models import Domain, DomainMove


class Command(BaseCommand):
    """
    Step 7 ("Cleanup") of the design doc's Domain Movement Procedure: delete a moved domain's
    stale rows from the database alias it moved *away from*.

    Only proceeds for a domain that is not currently mid-move (`Domain.moving` is `False`) and
    whose current `database_alias` is not `default` (a domain can only have been moved *to* a
    satellite by `move-domain`, never *to* `default` by this tooling -- if `database_alias` is
    `default`, either the domain was never moved or it's already been moved back, and there is
    nothing on some other alias for this command to legitimately clean up). Until this command
    runs, rollback is a one-line `Domain.database_alias` flip back to the original alias with
    no data loss -- this command is what makes that no longer true, hence the confirmation
    safeguard.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("domain", help=_("Name of the previously-moved domain to clean up."))
        parser.add_argument(
            "--from",
            dest="from_alias",
            help=_(
                "The alias to delete the domain's stale rows from. Defaults to the "
                "`from_alias` of the domain's most recent completed DomainMove record onto its "
                "current alias. Required if no such record exists (e.g. the domain was moved "
                "by means other than 'move-domain')."
            ),
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help=_(
                "Required. Explicit acknowledgement that this permanently deletes data from "
                "'--from' with no way to roll back afterwards."
            ),
        )

    def handle(self, *args, **options):
        try:
            domain = Domain.objects.using("default").get(name=options["domain"])
        except Domain.DoesNotExist:
            raise CommandError(_("No domain named '{name}' exists.").format(name=options["domain"]))

        if domain.moving:
            raise CommandError(
                _(
                    "Domain '{name}' has moving=True -- a move is in progress. Wait for it to "
                    "finish (or fail cleanly) before cleaning up."
                ).format(name=domain.name)
            )
        if domain.database_alias == "default":
            raise CommandError(
                _(
                    "Domain '{name}' is currently on 'default' -- nothing to clean up (either "
                    "it was never moved, or it was already moved back)."
                ).format(name=domain.name)
            )

        move = (
            DomainMove.objects.using("default")
            .filter(domain=domain, status="completed", to_alias=domain.database_alias)
            .order_by("-cutover_at")
            .first()
        )

        from_alias = options["from_alias"] or (move and move.from_alias)
        if not from_alias:
            raise CommandError(
                _(
                    "No completed DomainMove record found for domain '{name}' onto its current "
                    "alias '{alias}'. Pass --from explicitly (the alias to delete the domain's "
                    "stale data from) if this domain was moved by means other than "
                    "'move-domain'."
                ).format(name=domain.name, alias=domain.database_alias)
            )
        if from_alias == domain.database_alias:
            raise CommandError(
                _(
                    "--from ('{alias}') is the domain's current alias; refusing to clean that up."
                ).format(alias=from_alias)
            )

        if move and move.monitoring_until and now() < move.monitoring_until:
            self.stdout.write(
                self.style.WARNING(
                    _(
                        "The recommended monitoring window for this move does not end until "
                        "{until}. Proceeding anyway since you're running this command, but "
                        "consider waiting."
                    ).format(until=move.monitoring_until)
                )
            )

        if not options["force"]:
            raise CommandError(
                _(
                    "Refusing to delete domain '{name}''s data from '{alias}' without --force. "
                    "This is permanent and cannot be rolled back afterwards -- re-run with "
                    "--force once you are certain."
                ).format(name=domain.name, alias=from_alias)
            )

        self.stdout.write(
            _("Deleting domain '{name}''s data from '{alias}'...").format(
                name=domain.name, alias=from_alias
            )
        )
        try:
            deleted = delete_domain_data(domain, from_alias)
        except DomainMoveError as e:
            raise CommandError(str(e)) from e

        for label, count in deleted.items():
            if count:
                self.stdout.write(f"  {label}: {count} row(s) deleted")

        if move:
            move.cleaned_up_at = now()
            move.status = "cleaned_up"
            move.save(update_fields=["cleaned_up_at", "status"])

        self.stdout.write(
            self.style.SUCCESS(
                _("Domain '{name}''s data removed from '{alias}'.").format(
                    name=domain.name, alias=from_alias
                )
            )
        )
