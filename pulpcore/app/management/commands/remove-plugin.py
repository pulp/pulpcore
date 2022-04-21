import time

from gettext import gettext as _

from django.apps import apps
from django.db import connection, IntegrityError
from django.db.migrations.exceptions import IrreversibleError
from django.db.models.signals import post_migrate
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand, call_command, CommandError

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.models import AccessPolicy, ContentAppStatus, Worker
from pulpcore.app.models.role import Role
from pulpcore.app.util import get_view_urlpattern

DROP_PLUGIN_TABLES_QUERY = """
DO $$
  BEGIN
    EXECUTE format('DROP TABLE %s',
                    (SELECT STRING_AGG(table_name, ', ')
                       FROM information_schema.tables
                         WHERE table_schema = 'public' AND table_name like '{app_label}_%'
                    )
                  );
  END
$$;
"""  # noqa


class Command(BaseCommand):
    """
    Django management command for removing a plugin.

    This command is in tech-preview.
    """

    help = (
        "[tech-preview] Disable a Pulp plugin and remove all the relevant data from the database. "
        "Destructive!"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "plugin_name",
            help=_("Name of a plugin to remove. E.g. file, container, rpm, pulp_2to3_migration."),
        )

    def _check_pulp_services(self):
        """
        Check if any pulp services are running and error out if they are.
        """
        is_pulp_running = True
        waiting_time = max(settings.CONTENT_APP_TTL, settings.WORKER_TTL)
        check_started = time.time()
        self.stdout.write(
            "Checking if Pulp services are running, it can take up to {}s...".format(waiting_time)
        )
        while is_pulp_running and (time.time() - check_started) < waiting_time:
            is_pulp_running = (
                ContentAppStatus.objects.online().exists()
                or Worker.objects.online_workers().exists()
            )
            time.sleep(2)

        if is_pulp_running:
            raise CommandError(
                "The command can't be used when Pulp services are running. Please stop the "
                "services: pulpcore-api, pulpcore-content and all pulpcore-worker@*."
            )

    def _remove_indirect_plugin_data(self, app_label):
        """
        Remove plugin data not accessible via plugin models.

        Specifically,
            - remove django content type by app_label (also auth permissions are removed by cascade)
            - remove default access policies related to the plugin with provided app_label
            - remove locked roles related to the plugin, do not touch the user defined ones.
        """
        ContentType.objects.filter(app_label=app_label).delete()
        app_config = apps.get_app_config(app_label)
        viewset_names = []
        role_names = []
        for viewset_batch in app_config.named_viewsets.values():
            for viewset in viewset_batch:
                viewset_names.append(get_view_urlpattern(viewset))
                role_names.extend(getattr(viewset, "LOCKED_ROLES", {}).keys())

        AccessPolicy.objects.filter(viewset_name__in=viewset_names, customized=False).delete()
        Role.objects.filter(name__in=role_names, locked=True).delete()

    def _remove_plugin_data(self, app_label):
        """
        Remove all plugin data.

        Removal happens via ORM to be sure that all relations are cleaned properly as well,
        e.g. Master-Detail, FKs to various content plugins in pulp-2to3-migration.

        In some cases, the order in which models are removed matters, e.g. FK is a part of
        uniqueness constraint. Try to remove such problematic models later.
        """

        models_to_delete = set(apps.all_models[app_label].values())
        prev_model_count = len(models_to_delete) + 1
        while models_to_delete and len(models_to_delete) < prev_model_count:
            # while there is something to delete and something is being deleted on each iteration
            removed_models = set()
            for model in models_to_delete:
                self.stdout.write(_("Removing model: {}").format(model))
                try:
                    model.objects.filter().delete()
                except IntegrityError:
                    continue
                else:
                    removed_models.add(model)

            prev_model_count = len(models_to_delete)
            models_to_delete = models_to_delete - removed_models

        if models_to_delete:
            # Never-happen case
            raise CommandError(
                (
                    "Data for the following models can't be removed: {}. Please contact plugin "
                    "maintainers."
                ).format(list(models_to_delete))
            )

        self._remove_indirect_plugin_data(app_label)

    def _drop_plugin_tables(self, app_label):
        """
        Drop plugin table with raw SQL.
        """
        with connection.cursor() as cursor:
            cursor.execute(DROP_PLUGIN_TABLES_QUERY.format(app_label=app_label))

    def _unapply_migrations(self, app_label):
        """
        Unapply migrations so the plugin can be installed/run django migrations again if needed.

        Make sure no post migration signals are connected/run (it's enough to disable only
        `populate_access_policy` and `populate_roles` for the requested plugin, so after
        migration is run, policies are not repopulated but there is no need for any of
        post_migrate operations to happen.)

        Then, try to unmigrate the clean way, and if it fails, fake it until you make it.
        A potential reason for the failure can be that some migrations are irreversible.
        """
        for app_config in pulp_plugin_configs():
            post_migrate.disconnect(
                sender=app_config, dispatch_uid="populate_access_policies_identifier"
            )
            post_migrate.disconnect(sender=app_config, dispatch_uid="populate_roles_identifier")
            if app_config.label == "core":
                post_migrate.disconnect(sender=app_config, dispatch_uid="delete_anon_identifier")

        try:
            call_command("migrate", app_label=app_label, migration_name="zero")
        except (IrreversibleError, Exception):
            # a plugin has irreversible migrations or some other problem, drop the tables and fake
            # that migrations are unapplied.
            self._drop_plugin_tables(app_label)
            call_command("migrate", app_label=app_label, migration_name="zero", fake=True)

    def handle(self, *args, **options):
        plugin_name = options["plugin_name"]
        if plugin_name == "core":
            raise CommandError(_("Please specify a plugin name, core can't be removed."))

        available_plugins = {app.label for app in pulp_plugin_configs()} - {"core"}
        if plugin_name not in available_plugins:
            raise CommandError(
                (
                    "Plugin name is incorrectly specified or plugin is not installed. Please "
                    "specify one of the following plugin names: {}."
                ).format(list(available_plugins))
            )

        self._check_pulp_services()

        self.stdout.write(_("Cleaning up the database for {} plugin...").format(plugin_name))
        self._remove_plugin_data(app_label=plugin_name)

        self.stdout.write(_("Unapplying {} plugin migrations...").format(plugin_name))
        self._unapply_migrations(app_label=plugin_name)

        self.stdout.write(
            (
                "Successfully removed the {} plugin data. It is ready to be uninstalled. "
                "NOTE: Please do uninstall, otherwise `pulp status` might not show you the correct "
                "list of plugins available."
            ).format(plugin_name)
        )
