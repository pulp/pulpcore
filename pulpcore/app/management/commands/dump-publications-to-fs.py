from gettext import gettext as _
import logging
import os

from django.core.exceptions import ObjectDoesNotExist
from django.core.management import BaseCommand, CommandError

from pulpcore.app.models import Publication, Distribution
from pulpcore.app.tasks.export import (
    _export_publication_to_file_system,
    _export_location_is_clean,
    UnexportableArtifactException,
)
from pulpcore.app.viewsets.base import NamedModelViewSet
from pulpcore.constants import FS_EXPORT_METHODS


class Command(BaseCommand):
    """Django management command for exporting full repositories to a location on disk."""

    help = _("Export full repositories to a location on disk.")

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument("--publication", required=False, help=_("A publication ID."))
        parser.add_argument(
            "--distribution-path-prefix",
            required=False,
            help=_("A filter for distributions whose base_path begins with the provided prefix."),
        )
        parser.add_argument(
            "--type",
            required=False,
            help=_("Only export publications of a particular type, e.g. 'rpm.rpm'"),
        )
        parser.add_argument(
            "--method",
            required=False,
            default=FS_EXPORT_METHODS.WRITE,
            choices=(
                FS_EXPORT_METHODS.WRITE,
                FS_EXPORT_METHODS.HARDLINK,
                FS_EXPORT_METHODS.SYMLINK,
            ),
            help=_("Method of exporting, e.g. write, hardlink, symlink"),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Don't export anything, just print what would be exported."),
        )
        parser.add_argument(
            "--allow-incomplete",
            action="store_true",
            help=_("Dump the publication even if not all files are available."),
        )
        parser.add_argument(
            "--allow-dirty",
            action="store_true",
            help=_(
                "Try to dump the publication even if the target directories already contain data."
            ),
        )
        parser.add_argument("dest", help=_("Place to drop the files."))

    def handle(self, *args, **options):
        """Implement the command."""
        to_export = []

        if options.get("publication") and options.get("distribution_path_prefix"):
            raise CommandError("Cannot provide both --publication and --distribution-path-prefix")
        # If a publication was specified just dump it there and exit
        elif options["publication"]:
            try:
                publication_pk = NamedModelViewSet.extract_pk(options["publication"])
            except Exception:
                publication_pk = options["publication"]
            publication = Publication.objects.get(pk=publication_pk)
            to_export.append((options["dest"], publication))

        # If no publication was specified go through the distributions and dump them if they
        # meet the criteria
        else:
            # If a base_path prefix was provided, filter out distributions with a base path
            # that doesn't start with the prefix
            if options.get("distribution_path_prefix"):
                distributions = Distribution.objects.filter(
                    base_path__startswith=options["distribution_path_prefix"]
                )
            else:
                distributions = Distribution.objects.all()

            # Filter out distributions that don't match the type specified (if any)
            if options["type"]:
                distributions = distributions.filter(pulp_type__startswith=options["type"])

            # For all matching distributions, if they have a publication, dump it in a directory
            # matching the original distribution structure
            for distribution in distributions:
                if distribution.publication:
                    publication = distribution.publication
                elif distribution.repository:
                    repository = distribution.repository
                    # Account for distributions serving the latest publication of a given repository
                    try:
                        publication = Publication.objects.filter(
                            repository_version__in=repository.versions.all(), complete=True
                        ).latest("repository_version", "pulp_created")
                        repo_path = os.path.join(options["dest"], distribution.base_path)
                        to_export.append((repo_path, publication))
                    except ObjectDoesNotExist:
                        logging.warn(
                            "No publication found for the repo published at '{}': skipping".format(
                                distribution.base_path
                            )
                        )

        # Go through all the target directories first, if any of them are dirty, print warnings
        # and exit - unless the user explicitly asked to go through with it anyway.
        if not options["allow_dirty"]:
            is_dirty = False
            for dest, publication in to_export:
                if not _export_location_is_clean(dest):
                    logging.error(
                        _("Directory '{}' must be empty to be used as an export location").format(
                            dest
                        )
                    )
                    is_dirty = True

            if is_dirty:
                raise CommandError(_("Cannot export to directories that contain existing data."))

        if options["dry_run"]:
            for dest, publication in to_export:
                logging.info(
                    "Will write publication '{}' to '{}'".format(str(publication.pk), dest)
                )
        else:
            for dest, publication in to_export:
                self.export_publication(
                    dest, publication, options["method"], options["allow_incomplete"]
                )
                logging.info("Wrote publication '{}' to '{}'".format(str(publication.pk), dest))

    def export_publication(self, dest, publication, method, allow_incomplete):
        """Export a single publication to a provided destination.

        Args:
            dest (str): Directory to dump the publication data into
            publication (UUID): Publication ID
        """
        try:
            _export_publication_to_file_system(
                dest,
                publication,
                method=method,
                allow_missing=allow_incomplete,
            )
        except UnexportableArtifactException:
            raise CommandError(
                _(
                    "An artifact present in this publication is not available, please download "
                    "the full contents of this repository or else use the --allow-incomplete flag."
                )
            )
