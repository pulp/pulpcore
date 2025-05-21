from gettext import gettext as _

from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.writer import MigrationWriter
from django.core.management import BaseCommand


class Command(BaseCommand):
    """Django management command to adjust migration dependencies to rebase on another plugin."""

    help = _("Adjust migration dependencies to rebase on another plugin.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help=_("Don't change anything."))
        parser.add_argument("app-label", help=_("App label of the migrations to rewire."))
        parser.add_argument("dependency-app-label", help=_("App label of the dependency."))
        parser.add_argument("dependency-migration", help=_("Prefix of the dependency migration."))

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        app_label = options["app-label"]
        dependency_app_label = options["dependency-app-label"]
        dependency_migration_prefix = options["dependency-migration"]

        loader = MigrationLoader(connection, replace_migrations=False)

        dependency_migration = loader.get_migration_by_prefix(
            dependency_app_label, dependency_migration_prefix
        )
        new_dependency = (dependency_app_label, dependency_migration.name)

        # Calculate list of replaceable dependencies.
        rebase_node = loader.graph.node_map[new_dependency]
        ancestors = set(rebase_node.parents)
        replaceable_dependencies = set()
        while ancestors:
            rebase_node = ancestors.pop()
            ancestors.update(rebase_node.parents)
            if rebase_node.key[0] == dependency_app_label:
                replaceable_dependencies.add(rebase_node.key)

        # Identify all migrations that need to be adjusted.
        affected_nodes = [
            node
            for node in loader.graph.node_map.values()
            if node.key[0] == app_label
            and any(
                (
                    dependency
                    for dependency in loader.disk_migrations[node.key].dependencies
                    if dependency in replaceable_dependencies
                )
            )
        ]

        for affected_node in affected_nodes:
            migration = loader.disk_migrations[affected_node.key]
            # Remove all replaceable dependencies.
            migration.dependencies = [
                dependency
                for dependency in migration.dependencies
                if dependency not in replaceable_dependencies
            ]
            # Identify if we have added / will add the dependency in an ancestor.
            ancestors = set(affected_node.parents)
            while ancestors:
                ancestor_node = ancestors.pop()
                ancestors.update(ancestor_node.parents)
                if ancestor_node in affected_nodes:
                    break
            else:
                migration.dependencies.append(new_dependency)

            print(_("Changing migration {}").format(affected_node.key))
            if not dry_run:
                writer = MigrationWriter(migration)
                with open(writer.path, "w") as output_file:
                    output_file.write(writer.as_string())
