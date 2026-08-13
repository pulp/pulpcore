from gettext import gettext as _

from django.core.management import BaseCommand, CommandError
from django.utils.timezone import now

from pulpcore.app.domain_move import DomainMoveError, delete_domain_data
from pulpcore.app.models import Domain, DomainMove


class Command(BaseCommand):
    """
    Step 7 ("Cleanup") of the domain move procedure: delete a moved domain's stale data-plane
    rows from the database alias it moved *away from* -- and, if that alias was a satellite
    (not `"default"`, which is always the domain's authoritative home regardless of which alias
    hosts its data), its now-stale replicated `Domain` metadata row too.

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

        # The domain's own metadata row on `from_alias` (replicated there by domain_sync.py back
        # when it was still hosted there) is stale now too -- unless `from_alias` is `"default"`,
        # which is *always* the authoritative home for every `Domain` row regardless of
        # `database_alias` (see domain_sync.py's module docstring); there is never a "replica" of
        # it to prune there, only a genuine satellite-to-satellite move leaves a stale replica
        # behind. `reconcile_domains_to_alias` would eventually prune a genuine stale replica as
        # "extra" on the next periodic/migrate-all-driven 'sync-domains' run regardless, but
        # there's no reason to wait: we're already past the confirmation safeguard above for
        # permanently deleting this domain's data from `from_alias`, so clean up its stale
        # `Domain` row too, right now, in the same pass.
        if from_alias != "default":
            Domain.objects.using(from_alias).filter(pulp_id=domain.pulp_id).delete()

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
