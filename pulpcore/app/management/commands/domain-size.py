from gettext import gettext as _

from django.core.management import BaseCommand, CommandError

from pulpcore.app.domain_move import estimate_domain_size
from pulpcore.app.models import Domain


class Command(BaseCommand):
    """
    Report per-model row counts (and each table's total on-disk size, for scale/context) for a
    domain's data-plane objects on its current database alias.

    Standalone tooling for Step 1 ("Preparation") of the design doc's Domain Movement
    Procedure -- `move-domain` also prints this same report automatically before starting a
    move, so this command exists for an operator to check ahead of time (e.g. while deciding
    which domain is worth moving) without actually starting one.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("domain", help=_("Name of the domain to report on."))

    def handle(self, *args, **options):
        try:
            domain = Domain.objects.using("default").get(name=options["domain"])
        except Domain.DoesNotExist:
            raise CommandError(_("No domain named '{name}' exists.").format(name=options["domain"]))

        self.stdout.write(
            _("Domain '{name}' (currently on alias '{alias}'):").format(
                name=domain.name, alias=domain.database_alias
            )
        )
        report = estimate_domain_size(domain, domain.database_alias)
        total_rows = 0
        any_rows = False
        for row in report:
            if row["row_count"] == 0:
                continue
            any_rows = True
            total_rows += row["row_count"]
            self.stdout.write(
                "  {model}: {rows} row(s) (table '{table}' total size: {size} bytes)".format(
                    model=row["model"],
                    rows=row["row_count"],
                    table=row["table"],
                    size=row["table_total_size_bytes"],
                )
            )
        if not any_rows:
            self.stdout.write(_("  No data-plane rows found for this domain."))
        else:
            self.stdout.write(_("Total rows across all models: {n}").format(n=total_rows))
