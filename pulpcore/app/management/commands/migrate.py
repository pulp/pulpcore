from django.core.management.commands.migrate import Command as _DjangoMigrateCommand
from django.db.utils import DEFAULT_DB_ALIAS

from pulpcore.app.contexts import with_migration_alias


class Command(_DjangoMigrateCommand):
    """
    Wrapper around Django's built-in migrate command that also records which
    --database alias is currently being migrated, for the duration of the run.
    """

    help = _DjangoMigrateCommand.__doc__

    def handle(self, *args, **options):
        alias = options.get("database") or DEFAULT_DB_ALIAS
        with with_migration_alias(alias):
            return super().handle(*args, **options)
