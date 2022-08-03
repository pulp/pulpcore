from collections import defaultdict
from gettext import gettext as _

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.migration import SwappableTuple
from django.db.migrations.optimizer import MigrationOptimizer
from django.db.migrations.writer import MigrationWriter
from django.conf import settings
from django.core.management import BaseCommand


def print_stats(migration):
    operations = migration.operations
    migration_types = defaultdict(int)
    for operation in operations:
        migration_types[operation.__class__.__name__] += 1
    for key, value in migration_types.items():
        print(f"{value: 4} {key}")
    print("---")
    print(_("Total: {count}").format(count=len(operations)))


class Command(BaseCommand):
    """
    Django management command to optimize a migration.
    """

    help = _("Optimize a migration.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help=_("Don't change anything."))
        parser.add_argument(
            "--stat", action="store_true", help=_("Print statistics about operations.")
        )
        parser.add_argument("app-label", help=_("App label of the migrations to optimize."))
        parser.add_argument("migration", help=_("Prefix of the migration to optimize."))

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        stat = options.get("stat", False)
        app_label = options["app-label"]
        migration_prefix = options["migration"]

        loader = MigrationLoader(connection)

        migration = loader.get_migration_by_prefix(app_label, migration_prefix)

        print(_("Optimizing migration {}").format((migration.app_label, migration.name)))
        if stat:
            print(_("=== Old Migration Summary ==="))
            print_stats(migration)

        new_dependencies = []
        for dependency in migration.dependencies:
            if (
                isinstance(dependency, SwappableTuple)
                and settings.AUTH_USER_MODEL == dependency.setting
            ):
                new_dependencies.append(("__setting__", "AUTH_USER_MODEL"))
            else:
                new_dependencies.append(dependency)

        optimizer = MigrationOptimizer()
        new_operations = optimizer.optimize(migration.operations, app_label)

        if new_operations != migration.operations:
            print(
                _("Changed from {old_count} to {new_count} operations.").format(
                    old_count=len(migration.operations), new_count=len(new_operations)
                )
            )
            if stat:
                print(_("=== New Migration Summary ==="))
                print_stats(migration)

            migration.operations = new_operations
            migration.dependencies = new_dependencies
            if not dry_run:
                writer = MigrationWriter(migration)
                with open(writer.path, "w") as output_file:
                    output_file.write(writer.as_string())
        else:
            print(_("No optimizations found."))
