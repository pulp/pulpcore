"""
Integration tests for scoped `Domain` replication (`pulpcore.app.domain_sync`).

See `test_multi_database_routing.py`'s module docstring for why these require a real `data_1`
alias (set via `PULP_DATABASES__data_1__*` env vars) to run at all, rather than skipping.
"""

import pytest

from pulpcore.app.domain_sync import (
    ensure_domain_on_alias,
    reconcile_domains_to_alias,
    replicate_domain_delete,
    replicate_domain_save,
)
from pulpcore.app.models import Domain

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def default_hosted_domain():
    """A domain that has never been moved -- stays on `default`."""
    domain = Domain.objects.create(
        name="sync-test-default-hosted",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/sync-test-default-hosted"},
    )
    yield domain
    domain.delete()


@pytest.fixture
def satellite_hosted_domain():
    """A domain already hosted on the satellite (as if created there, or already moved)."""
    domain = Domain.objects.create(
        name="sync-test-satellite-hosted",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/sync-test-satellite-hosted"},
        database_alias=SATELLITE_ALIAS,
    )
    yield domain
    domain.delete()


class TestReplicationScoping:
    def test_default_domain_replicates_to_satellite(self):
        default_domain = Domain.objects.using("default").get(name="default")

        replicate_domain_save(default_domain)

        assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=default_domain.pk).exists()

    def test_domain_hosted_on_default_is_not_replicated_to_satellite(self, default_hosted_domain):
        # The post_save signal already fired once on create(); assert it never reached the
        # satellite, since this domain doesn't belong there.
        assert not Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=default_hosted_domain.pk
        ).exists()

    def test_domain_hosted_on_satellite_is_replicated_only_there(self, satellite_hosted_domain):
        assert Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()

    def test_replicate_domain_delete_only_targets_current_alias(self, satellite_hosted_domain):
        assert Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()

        replicate_domain_delete(satellite_hosted_domain)

        assert not Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()


class TestEnsureDomainOnAlias:
    def test_seeds_row_on_alias_regardless_of_current_database_alias(self, default_hosted_domain):
        assert not Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=default_hosted_domain.pk
        ).exists()

        ensure_domain_on_alias(default_hosted_domain, SATELLITE_ALIAS)

        assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=default_hosted_domain.pk).exists()
        # database_alias on the seeded row still reflects "default" -- ensure_domain_on_alias is
        # a verbatim copy, not a cutover; move-domain flips database_alias itself, separately.
        replicated = Domain.objects.using(SATELLITE_ALIAS).get(pk=default_hosted_domain.pk)
        assert replicated.database_alias == "default"


class TestReconcileDomainsToAlias:
    def test_domain_hosted_elsewhere_is_not_flagged_missing(self, default_hosted_domain):
        report = reconcile_domains_to_alias(SATELLITE_ALIAS, dry_run=True)

        assert default_hosted_domain.pulp_id not in report["missing"]
        assert not Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=default_hosted_domain.pk
        ).exists()

    def test_domain_hosted_here_but_missing_is_reconciled(self, satellite_hosted_domain):
        # Simulate a replication failure: the satellite never actually got the row.
        Domain.objects.using(SATELLITE_ALIAS).filter(pk=satellite_hosted_domain.pk).delete()

        report = reconcile_domains_to_alias(SATELLITE_ALIAS)

        assert satellite_hosted_domain.pulp_id in report["missing"]
        assert Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()

    def test_domain_moved_away_is_pruned_as_extra(self, satellite_hosted_domain):
        assert Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()

        # Simulate a completed move away from the satellite (bypassing move-domain's own
        # explicit bookkeeping, since only the resulting database_alias flip matters here).
        satellite_hosted_domain.database_alias = "default"
        satellite_hosted_domain.save(update_fields=["database_alias"])

        report = reconcile_domains_to_alias(SATELLITE_ALIAS)

        assert satellite_hosted_domain.pulp_id in report["extra"]
        assert not Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()

    def test_dry_run_reports_extra_without_deleting(self, satellite_hosted_domain):
        satellite_hosted_domain.database_alias = "default"
        satellite_hosted_domain.save(update_fields=["database_alias"])

        report = reconcile_domains_to_alias(SATELLITE_ALIAS, dry_run=True)

        assert satellite_hosted_domain.pulp_id in report["extra"]
        assert Domain.objects.using(SATELLITE_ALIAS).filter(
            pk=satellite_hosted_domain.pk
        ).exists()
