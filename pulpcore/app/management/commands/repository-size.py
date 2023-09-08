import json
import re
import sys
from gettext import gettext as _

from argparse import RawDescriptionHelpFormatter
from django.core.management import BaseCommand, CommandError
from django.conf import settings

from pulpcore.app.models import Repository
from pulpcore.app.util import get_url, extract_pk


def gather_repository_sizes(repositories, include_versions=False, include_on_demand=False):
    """
    Creates a list containing the size report for given repositories.

    Each entry in the list will contain a dict with following minimal fields:
        - name: name of the repository
        - href: href of the repository
        - disk-size: size in bytes of all artifacts stored on disk in the repository

    Each entry can additionally have the optional fields if specified:
        - on-demand-size: approximate size in bytes of all on-demand artifacts in the repository
        - versions: size report list of each version in the repository

    The version list if specified will have the following fields:
        - version: the version number
        - disk-size: size in bytes of all artifacts stored on disk for this repository version
        - on-demand-size: if specified, the approx size in bytes of on-demand artifacts in version

    **Note**: With artifact deduplication and additive repository versions, the sum total of each
    repository version size might be greater than the actual size of the repository. Sizes
    calculated in this report are based on the stored sizes in Pulp's database, they do not take
    into account missing artifacts or incorrect/missing on-demand artifact sizes.
    """
    full_report = []
    for repo in repositories.order_by("name").iterator():
        try:
            repo = repo.cast()
            report = {"name": repo.name, "href": get_url(repo), "disk-size": repo.disk_size}
            if include_on_demand:
                report["on-demand-size"] = repo.on_demand_size
            if include_versions:
                versions = []
                try:
                    for version in repo.versions.iterator():
                        v_report = {"version": version.number, "disk-size": version.disk_size}
                        if include_on_demand:
                            v_report["on-demand-size"] = version.on_demand_size
                        versions.append(v_report)
                except Exception:
                    pass
                else:
                    report["versions"] = versions
        except Exception:
            continue
        else:
            full_report.append(report)

    return full_report


def href_list_handler(value):
    """Common list parsing for a string of hrefs."""
    r = rf"({settings.API_ROOT}(?:[-_a-zA-Z0-9]+/)?api/v3/repositories/[-_a-z]+/[-_a-z]+/[-a-f0-9]+/)"  # noqa: E501
    return re.findall(r, value)


class Command(BaseCommand):
    """Django management command for calculating the storage size of a repository."""

    help = __doc__ + gather_repository_sizes.__doc__

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--repositories",
            type=href_list_handler,
            required=False,
            help=_(
                "List of repository hrefs to generate the report from. Leave blank to include"
                " all repositories in all domains. Mutually exclusive with domain."
            ),
        )
        parser.add_argument(
            "--include-versions",
            action="store_true",
            help=_("Include repository versions in report"),
        )
        parser.add_argument(
            "--include-on-demand",
            action="store_true",
            help=_("Include the approximate on-demand artifact sizes"),
        )
        parser.add_argument(
            "--domain",
            default=None,
            required=False,
            help=_(
                "The pulp domain to gather the repositories from if specified. Mutually"
                " exclusive with repositories."
            ),
        )
        parser.formatter_class = RawDescriptionHelpFormatter

    def handle(self, *args, **options):
        """Implement the command."""
        domain = options.get("domain")
        repository_hrefs = options.get("repositories")
        if domain and repository_hrefs:
            raise CommandError(_("--domain and --repositories are mutually exclusive"))

        repositories = Repository.objects.all()
        if repository_hrefs:
            repos_ids = [extract_pk(r) for r in repository_hrefs]
            repositories = repositories.filter(pk__in=repos_ids)
        elif domain:
            repositories = repositories.filter(pulp_domain__name=domain)

        report = gather_repository_sizes(
            repositories,
            include_versions=options["include_versions"],
            include_on_demand=options["include_on_demand"],
        )
        json.dump(report, sys.stdout, indent=4)
        print()
