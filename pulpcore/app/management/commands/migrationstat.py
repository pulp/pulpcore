from gettext import gettext as _

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.core.management import BaseCommand


class Command(BaseCommand):
    """Django management command to dump static informations about a migration."""

    help = _("Dump static informations about a migration.")

    def add_arguments(self, parser):
        parser.add_argument("app-label", help=_("App label of the migrations."))
        parser.add_argument("prefix", help=_("Prefix of the migration."))

    def handle(self, *args, **options):
        app_label = options["app-label"]
        prefix = options["prefix"]

        loader = MigrationLoader(connection)

        migration = loader.get_migration_by_prefix(app_label, prefix)

        print(_("Looking at migration {migration}.").format(migration=migration))
        if migration.atomic is False:
            print(_("Migration is not atomic."))
        print(_("Dependencies:"))
        for dep in migration.dependencies:
            print("- ", ".".join(dep))
        print(_("Operation Summary:"))
        runlength = 0
        op_type = ""
        for op in migration.operations:
            if op_type == op.__class__.__name__:
                runlength += 1
            else:
                if runlength:
                    print(f"{runlength} X {op_type}")
                op_type = op.__class__.__name__
                runlength = 1
        if runlength:
            print(f"{runlength} X {op_type}")
