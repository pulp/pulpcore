from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError

from pulpcore.app.models import ContentView, Distribution, Domain, Repository
from pulpcore.app.util_content_view import (
    STATUS_NO_DOMAIN_ACCESS,
    STATUS_NO_VERSION,
    STATUS_OK,
    group_versions_by_domain,
    resolve_content_view_distributions,
    scatter_gather,
    user_can_view_domain,
)


@pytest.fixture
def domain(db):
    return Domain.objects.create(name=str(uuid4()))


@pytest.fixture
def other_domain(db):
    return Domain.objects.create(name=str(uuid4()))


@pytest.fixture
def repository(domain):
    return Repository.objects.create(name=str(uuid4()), pulp_domain=domain)


@pytest.fixture
def other_repository(other_domain):
    return Repository.objects.create(name=str(uuid4()), pulp_domain=other_domain)


def make_user(superuser=False):
    return get_user_model().objects.create(username=str(uuid4()), is_superuser=superuser)


class TestContentViewModel:
    def test_create_defaults(self, domain):
        content_view = ContentView.objects.create(name="cv1", pulp_domain=domain)

        assert content_view.pulp_domain == domain
        assert content_view.pulp_labels == {}
        assert content_view.description is None
        assert list(content_view.distributions.all()) == []

    def test_name_unique_per_domain_only(self, domain, other_domain):
        ContentView.objects.create(name="cv1", pulp_domain=domain)
        # Same name is fine in a different domain.
        ContentView.objects.create(name="cv1", pulp_domain=other_domain)

        with pytest.raises(IntegrityError):
            ContentView.objects.create(name="cv1", pulp_domain=domain)

    def test_distributions_m2m_is_bidirectional(self, domain, repository):
        content_view = ContentView.objects.create(name="cv1", pulp_domain=domain)
        distribution = Distribution.objects.create(
            name="dist1", base_path="dist1", pulp_domain=domain, repository=repository
        )

        content_view.distributions.add(distribution)

        assert list(content_view.distributions.all()) == [distribution]
        assert list(distribution.content_views.all()) == [content_view]

    def test_distributions_may_belong_to_other_domains(
        self, domain, other_domain, other_repository
    ):
        content_view = ContentView.objects.create(name="cv1", pulp_domain=domain)
        foreign_distribution = Distribution.objects.create(
            name="dist1", base_path="dist1", pulp_domain=other_domain, repository=other_repository
        )

        # No FK/domain constraint prevents linking a distribution from a different domain.
        content_view.distributions.add(foreign_distribution)

        assert list(content_view.distributions.all()) == [foreign_distribution]


class TestUserCanViewDomain:
    def test_none_user_denied(self, domain):
        assert user_can_view_domain(None, domain) is False

    def test_unauthenticated_user_denied(self, domain):
        assert user_can_view_domain(AnonymousUser(), domain) is False

    def test_superuser_always_allowed(self, domain):
        user = make_user(superuser=True)
        assert user_can_view_domain(user, domain) is True

    def test_model_level_permission_allowed(self, domain):
        user = make_user()
        user.has_perm = lambda perm, obj=None: perm == "core.view_domain" and obj is None
        assert user_can_view_domain(user, domain) is True

    def test_object_level_permission_allowed(self, domain):
        user = make_user()
        user.has_perm = lambda perm, obj=None: perm == "core.view_domain" and obj is domain
        assert user_can_view_domain(user, domain) is True

    def test_no_permission_denied(self, domain):
        user = make_user()
        user.has_perm = lambda perm, obj=None: False
        assert user_can_view_domain(user, domain) is False


class TestResolveContentViewDistributions:
    def test_ok_status_for_accessible_resolvable_distribution(self, domain, repository):
        user = make_user(superuser=True)
        content_view = ContentView.objects.create(name="cv", pulp_domain=domain)
        distribution = Distribution.objects.create(
            name="d1", base_path="d1", pulp_domain=domain, repository=repository
        )
        content_view.distributions.add(distribution)

        resolutions = resolve_content_view_distributions(content_view, user)

        assert len(resolutions) == 1
        [resolution] = resolutions
        assert resolution.distribution == distribution
        assert resolution.domain == domain
        assert resolution.status == STATUS_OK
        assert resolution.repository_version == repository.latest_version()

    def test_no_version_status_for_distribution_without_source(self, domain):
        user = make_user(superuser=True)
        content_view = ContentView.objects.create(name="cv", pulp_domain=domain)
        # No repository, repository_version, or publication set -- nothing to resolve.
        distribution = Distribution.objects.create(name="d2", base_path="d2", pulp_domain=domain)
        content_view.distributions.add(distribution)

        [resolution] = resolve_content_view_distributions(content_view, user)

        assert resolution.status == STATUS_NO_VERSION
        assert resolution.repository_version is None

    def test_no_domain_access_status_for_inaccessible_domain(
        self, domain, other_domain, other_repository
    ):
        user = make_user()
        user.has_perm = lambda perm, obj=None: False  # no access anywhere
        content_view = ContentView.objects.create(name="cv", pulp_domain=domain)
        distribution = Distribution.objects.create(
            name="d3", base_path="d3", pulp_domain=other_domain, repository=other_repository
        )
        content_view.distributions.add(distribution)

        [resolution] = resolve_content_view_distributions(content_view, user)

        assert resolution.status == STATUS_NO_DOMAIN_ACCESS
        assert resolution.repository_version is None

    def test_mixed_statuses_and_grouping_excludes_non_ok(
        self, domain, other_domain, repository, other_repository
    ):
        user = make_user()
        # User can view `domain` but not `other_domain`.
        user.has_perm = lambda perm, obj=None: perm == "core.view_domain" and obj == domain

        content_view = ContentView.objects.create(name="cv", pulp_domain=domain)
        ok_distribution = Distribution.objects.create(
            name="ok", base_path="ok", pulp_domain=domain, repository=repository
        )
        no_access_distribution = Distribution.objects.create(
            name="na", base_path="na", pulp_domain=other_domain, repository=other_repository
        )
        no_version_distribution = Distribution.objects.create(
            name="nv", base_path="nv", pulp_domain=domain
        )
        content_view.distributions.add(
            ok_distribution, no_access_distribution, no_version_distribution
        )

        resolutions = resolve_content_view_distributions(content_view, user)
        by_pk = {r.distribution.pk: r for r in resolutions}

        assert by_pk[ok_distribution.pk].status == STATUS_OK
        assert by_pk[no_access_distribution.pk].status == STATUS_NO_DOMAIN_ACCESS
        assert by_pk[no_version_distribution.pk].status == STATUS_NO_VERSION

        # Edge case: all sources inaccessible/stale except one -- grouping must silently
        # exclude the rest rather than erroring.
        grouped = group_versions_by_domain(resolutions)
        assert list(grouped.keys()) == [domain]
        assert grouped[domain] == [repository.latest_version()]

    def test_all_inaccessible_yields_empty_grouping(self, domain, other_domain, other_repository):
        user = make_user()
        user.has_perm = lambda perm, obj=None: False

        content_view = ContentView.objects.create(name="cv", pulp_domain=domain)
        distribution = Distribution.objects.create(
            name="na", base_path="na", pulp_domain=other_domain, repository=other_repository
        )
        content_view.distributions.add(distribution)

        resolutions = resolve_content_view_distributions(content_view, user)
        assert group_versions_by_domain(resolutions) == {}


class TestScatterGather:
    @staticmethod
    def _make_repos(domain, names):
        return [Repository.objects.create(name=n, pulp_domain=domain) for n in names]

    def test_no_domains_returns_empty(self):
        page, total = scatter_gather(
            {}, lambda versions: Repository.objects.none(), order_by="name", limit=10
        )
        assert page == []
        assert total == 0

    def test_no_domains_returns_empty_without_count(self):
        page, total = scatter_gather(
            {},
            lambda versions: Repository.objects.none(),
            order_by="name",
            limit=10,
            count=False,
        )
        assert page == []
        assert total is None

    def test_single_domain_uses_native_ordering_and_slicing(self, domain):
        self._make_repos(domain, ["c", "a", "b"])

        def build_queryset(versions):
            return Repository.objects.filter(pulp_domain=domain).order_by("name")

        page, total = scatter_gather(
            {domain: ["v1"]}, build_queryset, order_by="name", limit=2, offset=1
        )

        assert total == 3
        assert [r.name for r in page] == ["b", "c"]

    def test_single_domain_skips_count_when_requested(self, domain):
        self._make_repos(domain, ["a", "b"])

        def build_queryset(versions):
            return Repository.objects.filter(pulp_domain=domain).order_by("name")

        page, total = scatter_gather(
            {domain: ["v1"]}, build_queryset, order_by="name", limit=10, count=False
        )

        assert total is None
        assert [r.name for r in page] == ["a", "b"]

    def test_multi_domain_merges_sorts_and_paginates(self, domain, other_domain):
        self._make_repos(domain, ["apple", "cherry"])
        self._make_repos(other_domain, ["banana", "date"])

        def build_queryset(versions):
            (current_domain,) = versions
            return Repository.objects.filter(pulp_domain=current_domain).order_by("name")

        versions_by_domain = {domain: [domain], other_domain: [other_domain]}

        page1, total1 = scatter_gather(
            versions_by_domain, build_queryset, order_by="name", limit=2, offset=0
        )
        assert total1 == 4
        assert [r.name for r in page1] == ["apple", "banana"]

        page2, total2 = scatter_gather(
            versions_by_domain, build_queryset, order_by="name", limit=2, offset=2
        )
        assert total2 == 4
        assert [r.name for r in page2] == ["cherry", "date"]

    def test_multi_domain_descending_order(self, domain, other_domain):
        self._make_repos(domain, ["apple", "cherry"])
        self._make_repos(other_domain, ["banana", "date"])

        def build_queryset(versions):
            (current_domain,) = versions
            return Repository.objects.filter(pulp_domain=current_domain).order_by("-name")

        versions_by_domain = {domain: [domain], other_domain: [other_domain]}

        page, total = scatter_gather(
            versions_by_domain,
            build_queryset,
            order_by="name",
            descending=True,
            limit=4,
        )

        assert total == 4
        assert [r.name for r in page] == ["date", "cherry", "banana", "apple"]

    def test_multi_domain_multi_field_order(self, domain, other_domain):
        Repository.objects.create(name="same", pulp_domain=domain, description="b")
        Repository.objects.create(name="same", pulp_domain=other_domain, description="a")

        def build_queryset(versions):
            (current_domain,) = versions
            return Repository.objects.filter(pulp_domain=current_domain).order_by(
                "name", "description"
            )

        versions_by_domain = {domain: [domain], other_domain: [other_domain]}

        page, total = scatter_gather(
            versions_by_domain,
            build_queryset,
            order_by=("name", "description"),
            limit=2,
        )

        assert total == 2
        assert [r.description for r in page] == ["a", "b"]

    def test_multi_domain_over_fetch_bound_excludes_out_of_range_rows(self, domain, other_domain):
        # Each domain is over-fetched only to `limit + offset` rows -- a lower-ranked row
        # from one domain that wouldn't make the final page must not be fetched needlessly,
        # but a higher-ranked one that does make the page must still show up correctly.
        self._make_repos(domain, ["a1", "a2", "a3"])
        self._make_repos(other_domain, ["b1"])

        def build_queryset(versions):
            (current_domain,) = versions
            return Repository.objects.filter(pulp_domain=current_domain).order_by("name")

        versions_by_domain = {domain: [domain], other_domain: [other_domain]}

        page, total = scatter_gather(
            versions_by_domain, build_queryset, order_by="name", limit=2, offset=0
        )

        assert total == 4
        assert [r.name for r in page] == ["a1", "a2"]
