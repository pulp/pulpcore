"""
Regression test: Domain.default_content_guard is a real, DB-enforced foreign key, and Domain
rows always live in 'default' (control-plane). Postgres has no cross-database foreign keys, so
setting default_content_guard to a ContentGuard that only exists on a satellite alias violated
that FK the moment the Domain row was written.

content_guard_sync.replicate_content_guard_to_default gives 'default' its own local copy of the
guard -- same pulp_id, same owning domain, including the concrete subclass's own fields (it's a
MasterModel detail model) and, for a CompositeContentGuard, its child guards and 'guards'
membership -- so the FK can validate without a cross-database relationship. The replica is kept
in sync by ContentGuard's AFTER_SAVE/BEFORE_DELETE hooks whenever it's edited or deleted
afterwards.
"""

import uuid

import pytest

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import CompositeContentGuard, ContentGuard, Domain, HeaderContentGuard

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


def _delete_guards_everywhere(satellite_domain, *pks):
    """Delete ContentGuard rows by pk from both 'default' and the satellite alias, each under
    matching ambient context. Deleting a MasterModel detail row (e.g. HeaderContentGuard) is a
    multi-table cascade: Django's collector re-queries the concrete-subclass table, sometimes
    with a restricted field set, and MasterModel.__init__ handling a deferred field on that
    re-fetched row falls back to ambient routing -- so a mismatched ambient context here can 404
    on a row that's actually still there. See content_guard_sync.
    remove_content_guard_default_replica's docstring for the same issue on the production path.
    """
    with with_domain(Domain.objects.get(name="default")):
        ContentGuard.objects.using("default").filter(pk__in=pks).delete()
    with with_domain(satellite_domain):
        ContentGuard.objects.using(SATELLITE_ALIAS).filter(pk__in=pks).delete()


@pytest.fixture
def satellite_domain():
    domain = Domain.objects.create(
        name=f"guard-replication-{uuid.uuid4().hex[:10]}",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/guard-replication-domain"},
        database_alias=SATELLITE_ALIAS,
    )
    yield domain
    domain.delete()


class TestDefaultContentGuardReplication:
    def test_simple_guard_replicates_before_fk_write(self, satellite_domain):
        with with_domain(satellite_domain):
            guard = HeaderContentGuard.objects.create(
                name=f"guard-{uuid.uuid4()}",
                pulp_domain=satellite_domain,
                header_name="X-Test",
                header_value="secret",
            )
        try:
            satellite_domain.default_content_guard = guard
            satellite_domain.save()  # must not raise IntegrityError (FK violation)

            replica = ContentGuard.objects.using("default").get(pk=guard.pk).cast()
            assert isinstance(replica, HeaderContentGuard)
            assert replica.header_name == "X-Test"
            assert replica.header_value == "secret"
            assert replica.pulp_domain_id == satellite_domain.pk
        finally:
            satellite_domain.default_content_guard = None
            satellite_domain.save()
            _delete_guards_everywhere(satellite_domain, guard.pk)

    def test_composite_guard_replicates_children_and_membership(self, satellite_domain):
        with with_domain(satellite_domain):
            child = HeaderContentGuard.objects.create(
                name=f"child-{uuid.uuid4()}",
                pulp_domain=satellite_domain,
                header_name="X-Child",
                header_value="v",
            )
            composite = CompositeContentGuard.objects.create(
                name=f"composite-{uuid.uuid4()}", pulp_domain=satellite_domain
            )
            composite.guards.add(child)
        try:
            satellite_domain.default_content_guard = composite
            satellite_domain.save()

            default_composite = ContentGuard.objects.using("default").get(pk=composite.pk).cast()
            assert isinstance(default_composite, CompositeContentGuard)
            child_pks_on_default = set(
                default_composite.guards.using("default").values_list("pk", flat=True)
            )
            assert child_pks_on_default == {child.pk}
            assert ContentGuard.objects.using("default").filter(pk=child.pk).exists()
        finally:
            satellite_domain.default_content_guard = None
            satellite_domain.save()
            _delete_guards_everywhere(satellite_domain, composite.pk, child.pk)

    def test_update_on_satellite_resyncs_default_replica(self, satellite_domain):
        with with_domain(satellite_domain):
            guard = HeaderContentGuard.objects.create(
                name=f"guard-{uuid.uuid4()}",
                pulp_domain=satellite_domain,
                header_name="X-Test",
                header_value="v1",
            )
        satellite_domain.default_content_guard = guard
        satellite_domain.save()
        try:
            with with_domain(satellite_domain):
                guard_fresh = HeaderContentGuard.objects.using(SATELLITE_ALIAS).get(pk=guard.pk)
                guard_fresh.header_value = "v2"
                guard_fresh.save()

            replica = HeaderContentGuard.objects.using("default").get(pk=guard.pk)
            assert replica.header_value == "v2"
        finally:
            satellite_domain.default_content_guard = None
            satellite_domain.save()
            _delete_guards_everywhere(satellite_domain, guard.pk)

    def test_delete_on_satellite_removes_default_replica(self, satellite_domain):
        with with_domain(satellite_domain):
            guard = HeaderContentGuard.objects.create(
                name=f"guard-{uuid.uuid4()}",
                pulp_domain=satellite_domain,
                header_name="X-Test",
                header_value="v1",
            )
        satellite_domain.default_content_guard = guard
        satellite_domain.save()
        satellite_domain.default_content_guard = None
        satellite_domain.save()
        try:
            assert ContentGuard.objects.using("default").filter(pk=guard.pk).exists()
            with with_domain(satellite_domain):
                HeaderContentGuard.objects.using(SATELLITE_ALIAS).get(pk=guard.pk).delete()

            assert not ContentGuard.objects.using("default").filter(pk=guard.pk).exists()
        finally:
            _delete_guards_everywhere(satellite_domain, guard.pk)
