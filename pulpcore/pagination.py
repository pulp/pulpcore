from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination

from pulpcore.app.models import RepositoryVersion
from pulpcore.app.util import resolve_prn, resolve_repository_version_href


class RepositoryVersionSummaryPagination(LimitOffsetPagination):
    """Use the persisted repository-version summary for unfiltered content counts."""

    def paginate_queryset(self, queryset, request, view=None):
        self._request = request
        return super().paginate_queryset(queryset, request, view)

    def _get_repository_version(self, href):
        """Resolve a repository-version PRN or numbered API href in this domain."""
        if href.startswith("prn:"):
            model, version_pk = resolve_prn(href)
            if model is not RepositoryVersion:
                return None
            return RepositoryVersion.objects.get(
                pk=version_pk,
                repository__pulp_domain=self._request.pulp_domain,
            )

        # API hrefs identify a version by repository and version number, not UUID.
        try:
            href_kwargs = resolve_repository_version_href(href)
        except ValidationError:
            return None
        return RepositoryVersion.objects.get(
            repository__pulp_id=href_kwargs["repository_pk"],
            number=int(href_kwargs["number"]),
            repository__pulp_domain=self._request.pulp_domain,
        )

    def get_count(self, queryset):
        # Map each supported repository-version filter to the corresponding summary helper.
        version_filters = {
            "repository_version": "count",
            "repository_version_added": "added_count",
            "repository_version_removed": "removed_count",
        }
        # Only one version filter can define the summary being requested; otherwise use DB count.
        selected_filters = [key for key in version_filters if key in self._request.query_params]
        if len(selected_filters) != 1:
            return super().get_count(queryset)
        version_filter = selected_filters[0]
        repository_version_href = self._request.query_params[version_filter]

        # A summary is exact for a completed, immutable repository version.  Only use it for
        # the unfiltered content query; arbitrary filters require the database count.
        if any(
            key not in {"repository_version", "limit", "offset", "ordering", "fields"}
            for key in self._request.query_params
        ):
            return super().get_count(queryset)

        try:
            version = self._get_repository_version(repository_version_href)
            # Incomplete or unresolvable versions must use the normal exact count.
            if version is None or not version.complete:
                return super().get_count(queryset)
            pulp_type = queryset.model.get_pulp_type()
            return getattr(version, version_filters[version_filter])(pulp_type)
        except (RepositoryVersion.DoesNotExist, ValidationError, ValueError):
            return super().get_count(queryset)
