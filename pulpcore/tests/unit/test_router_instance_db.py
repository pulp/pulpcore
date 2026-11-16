"""
Regression tests: PulpDomainRouter._resolve_db ignored an already-persisted instance's own
_state.db, falling back to ambient (domain-context) routing even when the instance itself
already knows exactly which alias it lives on. Two concrete failures this caused:

1. Loading a Repository via .using(SATELLITE_ALIAS) and saving it outside any with_domain()
   context inserted a duplicate row on 'default' instead of updating the satellite row.
2. Loading a RepositoryVersion via .using(SATELLITE_ALIAS) and accessing .repository raised
   Repository.DoesNotExist, because Django passes the *child* instance (the RepositoryVersion)
   as the routing hint when resolving the parent (Repository) model's alias, and Repository has
   no pulp_domain of its own to fall back on -- so without honoring the hint instance's own
   _state.db, this fell through to ambient context (wrong alias) instead.
"""

import uuid

import pytest
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Repository, RepositoryVersion

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    # Domain replication to the satellite is deferred via transaction.on_commit (see
    # domain_sync.on_domain_post_save), which never fires under pytest-django's test-wrapping
    # transaction unless explicitly flushed like this.
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"router-instdb-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/router-instdb-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestRouterHonorsLoadedInstanceDb:
    def test_save_outside_domain_context_updates_not_duplicates(self, satellite_domain):
        with with_domain(satellite_domain):
            repo = Repository.objects.create(name=str(uuid.uuid4()), pulp_domain=satellite_domain)
        try:
            # No with_domain() here: ambient context is 'default'. Loading explicitly via
            # .using(SATELLITE_ALIAS) should still save back to the satellite, not 'default'.
            repo_fresh = Repository.objects.using(SATELLITE_ALIAS).get(pk=repo.pk)
            repo_fresh.description = "updated with no ambient domain context"
            repo_fresh.save()

            assert (
                Repository.objects.using(SATELLITE_ALIAS).get(pk=repo.pk).description
                == "updated with no ambient domain context"
            )
            assert not Repository.objects.using("default").filter(pk=repo.pk).exists()
        finally:
            Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()

    def test_repository_version_fk_traversal_uses_own_alias(self, satellite_domain):
        with with_domain(satellite_domain):
            repo = Repository.objects.create(name=str(uuid.uuid4()), pulp_domain=satellite_domain)
            version = repo.versions.first()
        try:
            # No with_domain(): ambient context is 'default', but the version (and its
            # repository) only exist on the satellite.
            version_fresh = RepositoryVersion.objects.using(SATELLITE_ALIAS).get(pk=version.pk)
            assert version_fresh.repository.pk == repo.pk
        finally:
            Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()
