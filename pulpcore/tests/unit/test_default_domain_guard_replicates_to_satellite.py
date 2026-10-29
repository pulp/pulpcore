"""
Regression test for review comment on PR #7862: domain_sync.domain_field_values copies
default_content_guard_id verbatim when replicating a Domain's fields to a satellite. A content
guard lives in 'default' unless its owning domain is mapped to a satellite alias (the common
case), but a domain mapped to a satellite alias is itself replicated there too (domain_sync.
_target_aliases), so writing that domain's fields -- including a default_content_guard_id
pointing at a 'default'-only guard -- to its own satellite alias violated the FK on that
satellite's copy of the row. Previously only a silently-logged IntegrityError, leaving that
satellite with a stale or missing Domain row.

domain_sync now gives the target alias its own local copy of the guard first (mirroring
content_guard_sync.replicate_content_guard_to_default, generalized to any alias), both when
replicating a live save (replicate_domain_save/_replicate_one_save) and when reconciling
(reconcile_domains_to_alias).
"""

import uuid

import pytest
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.domain_sync import reconcile_domains_to_alias
from pulpcore.app.models import ContentGuard, Domain, HeaderContentGuard

from .test_default_content_guard_replication import _delete_guards_everywhere
from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"default-guard-satellite-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/default-guard-satellite-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


@pytest.fixture
def guard_in_default(satellite_domain):
    # The common case per content_guard_sync's own docstring: a guard lives in 'default' unless
    # its owning domain is mapped to a satellite alias.
    with with_domain(Domain.objects.get(name="default")):
        guard = HeaderContentGuard.objects.create(
            name=f"default-domain-guard-{uuid.uuid4().hex[:8]}",
            header_name="X-Test-Guard",
            header_value="secret",
        )
    yield guard
    _delete_guards_everywhere(satellite_domain, guard.pk)


class TestSatelliteDomainGuardReplicatesToOwnAlias:
    def test_live_save_replicates_guard_before_writing_fk(self, satellite_domain, guard_in_default):
        with TestCase.captureOnCommitCallbacks(execute=True):
            satellite_domain.default_content_guard = guard_in_default
            satellite_domain.save()

        satellite_replica = Domain.objects.using(SATELLITE_ALIAS).get(pk=satellite_domain.pk)
        assert satellite_replica.default_content_guard_id == guard_in_default.pk
        assert ContentGuard.objects.using(SATELLITE_ALIAS).filter(pk=guard_in_default.pk).exists()

    def test_reconcile_replicates_guard_before_writing_fk(self, satellite_domain, guard_in_default):
        # Bypass the live on_commit-deferred path entirely: set the FK directly on 'default'
        # without ever replicating, then let reconcile_domains_to_alias do the catch-up write.
        Domain.objects.using("default").filter(pk=satellite_domain.pk).update(
            default_content_guard_id=guard_in_default.pk
        )

        reconcile_domains_to_alias(SATELLITE_ALIAS)

        satellite_replica = Domain.objects.using(SATELLITE_ALIAS).get(pk=satellite_domain.pk)
        assert satellite_replica.default_content_guard_id == guard_in_default.pk
        assert ContentGuard.objects.using(SATELLITE_ALIAS).filter(pk=guard_in_default.pk).exists()
