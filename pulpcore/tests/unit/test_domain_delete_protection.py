"""
Regression test for review comments on PR #7862:

1. Domain always lives in 'default' (control-plane), so Django's native PROTECT check for a
   domain delete runs against 'default' and can't see data-plane rows living on the domain's own
   database_alias instead -- e.g. a Repository on a satellite. Without an alias-aware check, the
   domain was deletable on 'default' while repositories referencing it still existed on the
   satellite, which then surfaced as a silently-logged ProtectedError when the delete replicated
   there, leaving the satellite with an orphaned Domain-less Repository.

2. Domain save/delete replication ran synchronously from post_save/post_delete. If 'default's
   transaction later rolled back, the satellite had already been changed regardless. Both are now
   deferred via transaction.on_commit.
"""

import uuid

import pytest
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.db_router import atomic
from pulpcore.app.models import Domain, Repository
from pulpcore.exceptions import DomainProtectedError

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"delete-protect-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/delete-protect-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    pk = domain.pk
    yield domain
    # domain.delete() (if the test called it) clears domain.pk -- use the pk captured up front.
    Repository.objects.using(SATELLITE_ALIAS).filter(pulp_domain_id=pk).delete()
    Domain.objects.using("default").filter(pk=pk).delete()


class TestDomainDeleteCheckOwnAlias:
    def test_repository_on_satellite_blocks_domain_delete(self, satellite_domain):
        with with_domain(satellite_domain):
            repo = Repository.objects.create(name=f"{satellite_domain.name}-repo")
        assert repo._state.db == SATELLITE_ALIAS

        with pytest.raises(DomainProtectedError):
            satellite_domain.delete()

        # Must not have been deleted on 'default' either -- the whole point is that Django's
        # native (blind-to-the-satellite) PROTECT check alone would have let this succeed there.
        assert Domain.objects.using("default").filter(pk=satellite_domain.pk).exists()
        assert Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).exists()

    def test_domain_without_satellite_data_deletes_cleanly(self, satellite_domain):
        pk = satellite_domain.pk
        satellite_domain.delete()
        assert not Domain.objects.using("default").filter(pk=pk).exists()


class TestDomainReplicationDefersToCommit:
    def test_satellite_save_not_replicated_when_default_rolls_back(self):
        name = f"oncommit-domain-{uuid.uuid4().hex[:10]}"
        with pytest.raises(RuntimeError):
            with atomic(using="default"):
                Domain.objects.create(
                    name=name,
                    storage_class="pulpcore.app.models.storage.FileSystem",
                    database_alias=SATELLITE_ALIAS,
                )
                raise RuntimeError("force rollback")

        assert not Domain.objects.using("default").filter(name=name).exists()
        assert not Domain.objects.using(SATELLITE_ALIAS).filter(name=name).exists()

    def test_satellite_save_replicates_once_default_commits(self):
        name = f"oncommit-domain-committed-{uuid.uuid4().hex[:10]}"
        with TestCase.captureOnCommitCallbacks(execute=True):
            domain = Domain.objects.create(
                name=name,
                storage_class="pulpcore.app.models.storage.FileSystem",
                database_alias=SATELLITE_ALIAS,
            )
        try:
            assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=domain.pk).exists()
        finally:
            Domain.objects.using("default").filter(pk=domain.pk).delete()

    def test_satellite_delete_not_replicated_when_default_rolls_back(self):
        with TestCase.captureOnCommitCallbacks(execute=True):
            domain = Domain.objects.create(
                name=f"oncommit-delete-{uuid.uuid4().hex[:10]}",
                storage_class="pulpcore.app.models.storage.FileSystem",
                database_alias=SATELLITE_ALIAS,
            )
        assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=domain.pk).exists()

        try:
            with pytest.raises(RuntimeError):
                with atomic(using="default"):
                    Domain.objects.using("default").get(pk=domain.pk).delete()
                    raise RuntimeError("force rollback")

            # Rolled back on 'default': the satellite copy must survive too.
            assert Domain.objects.using("default").filter(pk=domain.pk).exists()
            assert Domain.objects.using(SATELLITE_ALIAS).filter(pk=domain.pk).exists()
        finally:
            Domain.objects.using("default").filter(pk=domain.pk).delete()
            Domain.objects.using(SATELLITE_ALIAS).filter(pk=domain.pk).delete()
