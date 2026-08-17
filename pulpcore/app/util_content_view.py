"""
Utilities for resolving a ContentView's Distributions into RepositoryVersions grouped by
domain, and for executing cross-domain "scatter/gather" queries against them.

These are the pieces a plugin (e.g. pulp_rpm) composes to implement its own nested
``content-views/{uuid}/search/...`` endpoints on top of the generic ``ContentView`` resource:

    resolutions = resolve_content_view_distributions(content_view, request.user)
    versions_by_domain = group_versions_by_domain(resolutions)
    page, total = scatter_gather(
        versions_by_domain,
        build_queryset=lambda versions: Package.objects.filter(
            pk__in=functools.reduce(operator.or_, (v.content for v in versions))
        ).order_by("name"),
        order_by=("name",),
        limit=limit,
        offset=offset,
    )

See the Plugin Writer's Guide for more on plugin/pulpcore boundaries:
https://pulpproject.org/pulpcore/docs/dev/learn/plugin-concepts/
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pulpcore.app.contexts import with_domain

# Distribution resolution statuses.
STATUS_OK = "ok"
STATUS_NO_DOMAIN_ACCESS = "no_domain_access"
STATUS_NO_VERSION = "no_version"


def user_can_view_domain(user, domain):
    """
    Returns True if ``user`` has read (view) access to ``domain``.

    This mirrors the same model/domain/object permission check used by
    ``pulpcore.app.global_access_conditions.has_domain_perms``, generalized to an arbitrary
    domain instead of only the current request's domain. This is what allows a ContentView to
    reference Distributions living in other domains while still enforcing RBAC, per-domain, at
    query time -- rather than at write time only.

    Deployments with a custom domain-membership model (e.g. an org-based permission backend)
    can make this reflect their own semantics by registering a Django authentication backend
    whose ``has_perm(user, "core.view_domain", obj=domain)`` answers accordingly; no changes to
    pulpcore or its plugins are required for that.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.has_perm("core.view_domain") or user.has_perm("core.view_domain", obj=domain)


@dataclass
class DistributionResolution:
    """The result of resolving a single Distribution linked to a ContentView."""

    distribution: Any
    domain: Any
    repository_version: Optional[Any]
    status: str


def resolve_content_view_distributions(content_view, user):
    """
    Resolve every Distribution linked to ``content_view`` to its current RepositoryVersion,
    classifying each one by accessibility/staleness. Never raises: distributions whose domain
    is no longer accessible, or that no longer resolve to a version (deleted distribution or
    repository version), are returned with a status instead of causing an error -- callers
    (search endpoints, and the ContentView detail serializer) decide how to surface that.

    Args:
        content_view (pulpcore.app.models.ContentView): The content view to resolve.
        user: The requesting user, used for the per-domain accessibility check.

    Returns:
        list[DistributionResolution]
    """
    resolutions = []
    for distribution in content_view.distributions.select_related("pulp_domain").all():
        domain = distribution.pulp_domain
        if not user_can_view_domain(user, domain):
            resolutions.append(
                DistributionResolution(distribution, domain, None, STATUS_NO_DOMAIN_ACCESS)
            )
            continue

        _repository, repository_version, _publication = (
            distribution.cast().get_repository_publication_and_version()
        )
        if repository_version is None:
            resolutions.append(
                DistributionResolution(distribution, domain, None, STATUS_NO_VERSION)
            )
        else:
            resolutions.append(
                DistributionResolution(distribution, domain, repository_version, STATUS_OK)
            )
    return resolutions


def group_versions_by_domain(resolutions):
    """
    Group the RepositoryVersions of "ok" resolutions by domain.

    This is the input scatter_gather (or a plugin's own equivalent loop) consumes -- lost-access
    and stale/deleted distributions (any non-"ok" status) are already excluded here, satisfying
    the "search silently excludes inaccessible distributions" requirement.

    Args:
        resolutions (list[DistributionResolution]):

    Returns:
        dict: Domain -> list[RepositoryVersion]
    """
    by_domain = defaultdict(list)
    for resolution in resolutions:
        if resolution.status == STATUS_OK:
            by_domain[resolution.domain].append(resolution.repository_version)
    return dict(by_domain)


def _sort_key(fields):
    def key(row):
        return tuple(
            (
                (value := (row[field] if isinstance(row, dict) else getattr(row, field))) is None,
                value,
            )
            for field in fields
        )

    return key


def scatter_gather(
    versions_by_domain: dict,
    build_queryset: Callable[[list], Any],
    *,
    order_by,
    limit: int,
    offset: int = 0,
    descending: bool = False,
    count: bool = True,
):
    """
    Execute ``build_queryset(versions)`` once per domain, inside that domain's routing context
    (``with_domain``), and merge the results into a single page.

    For the common case -- a ContentView resolving to a single domain -- this executes exactly
    one query with native ``ORDER BY``/``LIMIT``/``OFFSET`` (plus one ``COUNT`` if requested),
    identical in cost to a single-domain query. For multiple domains, each domain's queryset is
    over-fetched to ``limit + offset`` rows (sufficient, since a single domain can supply at most
    the entire final page), concatenated, re-sorted in Python, and sliced -- bounding worst-case
    cost to ``len(versions_by_domain) * (limit + offset)`` rather than the full dataset size.

    Args:
        versions_by_domain (dict): Domain -> list[RepositoryVersion], as returned by
            ``group_versions_by_domain``.
        build_queryset (callable): Given a list of RepositoryVersions (all belonging to the same
            domain), returns a QuerySet already filtered *and ordered* by ``order_by``
            (ascending), but not sliced. May return a ``.values()``/``.values_list()`` queryset.
        order_by (str or tuple[str]): One or more field names (without ``-`` prefixes) that
            ``build_queryset`` already orders by; used here to merge-sort rows fetched from
            multiple domains. Must match the ordering ``build_queryset`` applies.
        limit (int): Maximum number of rows to return.
        offset (int): Number of rows to skip.
        descending (bool): Whether the ordering above is descending. Applies uniformly to all
            ``order_by`` fields (sufficient for every current use case -- callers needing mixed
            per-field directions should pre-negate/annotate instead).
        count (bool): If True, also compute an exact total count across all domains.

    Returns:
        tuple: ``(page, total)``. ``page`` is a list of model instances (or dicts, if
            ``build_queryset`` uses ``.values()``/``.values_list()``) of length <= ``limit``.
            ``total`` is an int, or None if ``count=False`` (mirroring tang's typeahead search
            endpoints, which never compute a total).
    """
    fields = (order_by,) if isinstance(order_by, str) else tuple(order_by)
    domains = list(versions_by_domain.items())

    if not domains:
        return [], (0 if count else None)

    if len(domains) == 1:
        domain, versions = domains[0]
        with with_domain(domain):
            qs = build_queryset(versions)
            total = qs.count() if count else None
            page = list(qs[offset : offset + limit])
        return page, total

    rows = []
    total = 0 if count else None
    fetch_bound = limit + offset
    for domain, versions in domains:
        with with_domain(domain):
            qs = build_queryset(versions)
            if count:
                total += qs.count()
            rows.extend(qs[:fetch_bound])

    rows.sort(key=_sort_key(fields), reverse=descending)
    page = rows[offset : offset + limit]
    return page, total
