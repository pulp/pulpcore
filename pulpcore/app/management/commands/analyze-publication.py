from gettext import gettext as _

from django.core.management import BaseCommand, CommandError
from django.urls import reverse

from pulpcore.app.models import Publication, Artifact, Distribution
from pulpcore.app.util import get_view_name_for_model


class Command(BaseCommand):
    """Django management command for viewing files in a publication and the artifacts on disk."""

    help = _(__doc__)

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument("--publication", required=False, help=_("A publication ID."))
        parser.add_argument(
            "--distribution-base-path", required=False, help=_("A base_path of a distribution.")
        )
        parser.add_argument("--tabular", action="store_true", help=_("Display as a table"))

    def handle(self, *args, **options):
        """Implement the command."""

        if options["tabular"]:
            try:
                from prettytable import PrettyTable
            except ImportError:
                raise CommandError("'prettytable' package must be installed.")

        if not (options["publication"] or options["distribution_base_path"]):
            raise CommandError("Must provide either --publication or --distribution-base-path")
        elif options["publication"] and options["distribution_base_path"]:
            raise CommandError("Cannot provide both --publication and --distribution-base-path")
        elif options["publication"]:
            publication = Publication.objects.get(pk=options["publication"])
        else:
            distribution = Distribution.objects.get(base_path=options["distribution_base_path"])
            if distribution.publication:
                publication = distribution.publication
            elif distribution.repository:
                repository = distribution.repository
                publication = Publication.objects.filter(
                    repository_version__in=repository.versions.all(), complete=True
                ).latest("repository_version", "pulp_created")

        published_artifacts = publication.published_artifact.select_related(
            "content_artifact__artifact"
        ).order_by("relative_path")
        artifact_href_prefix = reverse(get_view_name_for_model(Artifact, "list"))

        if options["tabular"]:
            table = PrettyTable()
            table.field_names = ["Apparent path", "Storage path"]
            table.align = "l"  # left align values

        for pa in published_artifacts.iterator():
            ca = pa.content_artifact
            path = ca.artifact.file.path if ca.artifact else None
            artifact_id = ca.artifact_id
            artifact_href = (artifact_href_prefix + str(artifact_id)) if artifact_id else None
            if options["tabular"]:
                table.add_row([pa.relative_path, path or ""])
            else:
                print(pa.relative_path)
                print("└─ Storage path: {}".format(path))
                print("└─ Artifact href: {}".format(artifact_href))
                print()

        if options["tabular"]:
            print(table)
