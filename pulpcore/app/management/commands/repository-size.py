import json
import re
import sys
from argparse import RawDescriptionHelpFormatter
from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError

from pulpcore.app.models import Domain, Repository
from pulpcore.app.util import extract_pk, for_each_domain, get_url


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
        domain_name = options.get("domain")
        repository_hrefs = options.get("repositories")
        if domain_name and repository_hrefs:
            raise CommandError(_("--domain and --repositories are mutually exclusive"))

        # KI-08: `Repository` is data-plane, so an unqualified `Repository.objects.all()` (the
        # original shape of this command) -- or a `--domain` filter that only ever adds
        # `.filter(pulp_domain__name=...)` without also switching `.using(alias)` -- would only
        # ever see repositories that happen to live on `default`, even though the `--domain`
        # flag's own help text implies otherwise. All three call shapes below resolve the
        # relevant `Domain`/alias(es) explicitly and query with `.using(alias)`.
        report = []
        if repository_hrefs:
            repos_ids = [extract_pk(r) for r in repository_hrefs]
            # An href doesn't self-identify which alias its repository lives on, so check every
            # configured alias -- a given pk only ever matches on the one alias its domain
            # actually resides on; every other alias contributes an empty queryset.
            for alias in settings.DATABASES:
                repositories = Repository.objects.using(alias).filter(pk__in=repos_ids)
                report.extend(
                    gather_repository_sizes(
                        repositories,
                        include_versions=options["include_versions"],
                        include_on_demand=options["include_on_demand"],
                    )
                )
        elif domain_name:
            try:
                domain = Domain.objects.get(name=domain_name)
            except Domain.DoesNotExist:
                raise CommandError(_("Domain '{name}' does not exist.").format(name=domain_name))
            repositories = Repository.objects.using(domain.database_alias).filter(
                pulp_domain=domain
            )
            report = gather_repository_sizes(
                repositories,
                include_versions=options["include_versions"],
                include_on_demand=options["include_on_demand"],
            )
        else:

            def _gather_for_domain(domain, alias):
                repositories = Repository.objects.using(alias).filter(pulp_domain=domain)
                report.extend(
                    gather_repository_sizes(
                        repositories,
                        include_versions=options["include_versions"],
                        include_on_demand=options["include_on_demand"],
                    )
                )

            for_each_domain(_gather_for_domain)

        json.dump(report, sys.stdout, indent=4)
        print()
