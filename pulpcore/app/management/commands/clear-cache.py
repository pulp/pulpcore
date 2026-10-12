from gettext import gettext as _

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from pulpcore.app.models import Distribution, Repository
from pulpcore.app.util import cache_key, resolve_prn
from pulpcore.cache import Cache


def resolve_resources(resources, model):
    """Resolve resource names and PRNs to a queryset filter."""
    pks = []
    names = []
    for resource in resources:
        if resource.startswith("prn:"):
            try:
                resource_model, pk = resolve_prn(resource)
            except ValidationError as exc:
                raise CommandError(str(exc))
            if not issubclass(resource_model, model):
                raise CommandError(f"{resource} is not a {model.__name__} PRN.")
            pks.append(pk)
        else:
            names.append(resource)
    return Q(pk__in=pks) | Q(name__in=names)


class Command(BaseCommand):
    """Clear cached content responses."""

    help = "Clear cached content responses, optionally for repositories or distributions."

    def add_arguments(self, parser):
        """Set up arguments."""
        parser.add_argument(
            "--repository",
            action="append",
            help=_("Repository name or PRN to clear. May be specified more than once."),
        )
        parser.add_argument(
            "--distribution",
            action="append",
            help=_("Distribution name or PRN to clear. May be specified more than once."),
        )
        parser.add_argument(
            "--base-path",
            action="append",
            help=_("Base path to clear directly. May be specified more than once."),
        )
        parser.add_argument(
            "--domain",
            help=_("Domain name to clear or use with resource names."),
        )

    def handle(self, *args, **options):
        """Clear the selected content cache entries."""
        if not settings.CACHE_ENABLED:
            raise CommandError("Content caching is not enabled.")

        repositories = options["repository"]
        distributions = options["distribution"]
        base_paths = options["base_path"]
        if isinstance(repositories, str):
            repositories = [repositories]
        if isinstance(distributions, str):
            distributions = [distributions]
        if isinstance(base_paths, str):
            base_paths = [base_paths]
        domain = options["domain"]
        distribution_queryset = Distribution.objects.all()
        if base_paths:
            if settings.DOMAIN_ENABLED and not domain:
                raise CommandError(
                    "--domain is required with --base-path when domains are enabled."
                )
            base_keys = cache_key(base_paths, domain=domain)
        elif repositories:
            selected_repositories = Repository.objects.filter(
                resolve_resources(repositories, Repository)
            )
            distribution_queryset = distribution_queryset.filter(
                Q(repository__in=selected_repositories)
                | Q(repository_version__repository__in=selected_repositories)
                | Q(publication__repository_version__repository__in=selected_repositories)
            )
        elif distributions:
            distribution_queryset = distribution_queryset.filter(
                resolve_resources(distributions, Distribution)
            )

        if not base_paths:
            if domain:
                distribution_queryset = distribution_queryset.filter(pulp_domain__name=domain)
            if settings.DOMAIN_ENABLED:
                base_keys = [
                    cache_key(distribution.base_path, domain=distribution.pulp_domain)
                    for distribution in distribution_queryset.select_related("pulp_domain")
                ]
            else:
                base_keys = list(distribution_queryset.values_list("base_path", flat=True))

        cleared_entries = Cache().delete(base_key=base_keys) if base_keys else 0
        self.stdout.write(
            f"Cleared {cleared_entries} cache entr{'y' if cleared_entries == 1 else 'ies'}."
        )
