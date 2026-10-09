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
            result = super().handle(*args, **options)

        if alias != DEFAULT_DB_ALIAS:
            from pulpcore.app.db_router import is_multi_db_routing_active

            if is_multi_db_routing_active():
                # Must run after super().handle() fully returns, not from a post_migrate signal:
                # see apps.ensure_rbac_replicated_for_alias's docstring for why.
                from pulpcore.app.apps import ensure_rbac_replicated_for_alias

                ensure_rbac_replicated_for_alias(alias)

        return result
