from django.core.management.commands.migrate import Command as _DjangoMigrateCommand
from django.db.utils import DEFAULT_DB_ALIAS

from pulpcore.app.contexts import with_migration_alias


class Command(_DjangoMigrateCommand):
    """
    Thin wrapper around Django's own `migrate` command that records which `--database` alias is
    currently being migrated, for the duration of the run, in the `_current_migration_alias`
    ContextVar (see `pulpcore.app.contexts`).

    Why this exists: `PulpDomainRouter` (`db_router.py`) normally pins every control-plane model
    (e.g. `Task`) to `"default"` and every data-plane model to whatever `Domain` is in context --
    correct for ordinary request/task code, but wrong inside a `RunPython` data migration. Every
    pre-existing pulpcore/plugin migration was written before this router existed and queries its
    `apps.get_model(...)` ("historical state") models with no explicit `.using(...)`, exactly as
    Django's own docs recommend for the *single-database* case. Without this wrapper, migrating a
    satellite alias would silently have those bare queries redirected by the router to `default`
    instead of the satellite actually being migrated -- harmless (a no-op) as long as `default` has
    an identical, in-sync schema, but broken the instant `default` has already progressed further
    through the migration graph than the satellite currently being migrated (exactly the case for
    `migrate-all`, which always migrates `default` to completion first) -- see the design doc's
    router limitations. `PulpDomainRouter` uses this ContextVar to route bare queries against
    *historical* (migration-state) models to the alias actually being migrated instead, and only
    falls back to its normal control-/data-plane logic for models obtained the ordinary way (i.e.
    everywhere outside of a migration).

    This shadows Django's built-in `migrate` command for every entry point -- `manage.py migrate`,
    `call_command("migrate", ...)` (as used by `migrate-all`), and any third-party tooling that
    invokes it the same way -- because Django's command loader lets an installed app's management
    command override a built-in one of the same name.
    """

    help = _DjangoMigrateCommand.__doc__

    def handle(self, *args, **options):
        alias = options.get("database") or DEFAULT_DB_ALIAS
        with with_migration_alias(alias):
            return super().handle(*args, **options)
