from django.core.management.base import BaseCommand
from gettext import gettext as _
from django.db import connection
from pulpcore.app.models import RemoteArtifact


CHECK_COL_QUERY = """
SELECT COUNT(*)
FROM information_schema.columns
WHERE table_name = %s
AND column_name = %s;
"""

MODIFY_QUERY_TMPL = """
ALTER TABLE {}
ADD COLUMN {} TIMESTAMPTZ DEFAULT NULL;
"""

HELP = _(
    """
Enables patch backport of #6064 (https://github.com/pulp/pulpcore/pull/6064).

The fix prevents corrupted remotes from making content unreacahble by adding
a cooldown time, which is tracked by a new field, 'RemoteArtifact.failed_at'.
This command adds the field to the appropriate table.
"""
)


class Command(BaseCommand):
    help = HELP

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the migration in dry-run mode without saving changes",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        try:
            with connection.cursor() as cursor:
                # Check if column already exists
                table_name = RemoteArtifact._meta.db_table
                field_name = "failed_at"
                cursor.execute(CHECK_COL_QUERY, [table_name, field_name])
                field_exists = cursor.fetchone()[0] > 0
                if field_exists:
                    self._print_success(f"Field '{table_name}.{field_name}' already exists.")
                    self._print_success("Nothing to be done")
                    return

                # Add field to table
                self._print_info(f"Adding {field_name!r} column to {table_name!r}...")
                MODIFY_QUERY = MODIFY_QUERY_TMPL.format(table_name, field_name)
                if not dry_run:
                    cursor.execute(MODIFY_QUERY)
                    self._print_success("Done")
                else:
                    self._print_warn("[DRY-RUN] SQL that would be executed:")
                    self._print_info(MODIFY_QUERY)
        except Exception as e:
            self._print_error(f"Migration failed: {str(e)}")
            raise

    def _print_info(self, msg):
        self.stdout.write(msg)

    def _print_success(self, msg):
        self.stdout.write(self.style.SUCCESS(msg))

    def _print_error(self, msg):
        self.stdout.write(self.style.ERROR(msg))

    def _print_warn(self, msg):
        self.stdout.write(self.style.WARNING(msg))
