from rest_framework.exceptions import ValidationError
from rest_framework.pagination import LimitOffsetPagination

from pulpcore.app.models import RepositoryVersion, RepositoryVersionContentDetails
from pulpcore.app.util import get_viewset_for_model
from pulpcore.app.viewsets.custom_filters import RepoVersionHrefPrnFilter


class RepositoryVersionSummaryPagination(LimitOffsetPagination):
    """Use persisted summaries for safe, unfiltered content-list pagination counts.

    The summary is used only for completed repository versions, when exactly one
    repository-version filter is present, and when the requester can access the
    repository. All other requests fall back to
    the normal database count to preserve filtering and authorization semantics.
    """

    def paginate_queryset(self, queryset, request, view=None):
        self._request = request
        return super().paginate_queryset(queryset, request, view)

    def _get_repository_version(self, href):
        """Resolve an RV or repository reference using content-filter semantics."""
        try:
            version = RepoVersionHrefPrnFilter.get_repository_version(href)
        except (ValidationError, RepositoryVersion.DoesNotExist, ValueError):
            return None
        if version.repository.pulp_domain_id != self._request.pulp_domain.pk:
            return None
        return version

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
            key not in {version_filter, "limit", "offset", "ordering", "fields"}
            for key in self._request.query_params
        ):
            return super().get_count(queryset)

        try:
            version = self._get_repository_version(repository_version_href)
            # Incomplete or unresolvable versions must use the normal exact count.
            if version is None or not version.complete:
                return super().get_count(queryset)
            # Non-superusers can use cached summaries when they can view the repository.
            # Without this check, a global summary could bypass RBAC and reveal the
            # count of content from a repository they cannot access.
            if not self._request.user.is_superuser:
                repository = version.repository.cast()
                repository_viewset = get_viewset_for_model(type(repository))()
                repository_viewset.request = self._request
                if not repository_viewset.get_queryset().filter(pk=repository.pk).exists():
                    return super().get_count(queryset)
            pulp_type = queryset.model.get_pulp_type()
            count_type = {
                "repository_version": RepositoryVersionContentDetails.PRESENT,
                "repository_version_added": RepositoryVersionContentDetails.ADDED,
                "repository_version_removed": RepositoryVersionContentDetails.REMOVED,
            }[version_filter]
            if not version.has_count(pulp_type, count_type):
                return super().get_count(queryset)
            return getattr(version, version_filters[version_filter])(pulp_type)
        except (RepositoryVersion.DoesNotExist, ValidationError, ValueError):
            return super().get_count(queryset)
