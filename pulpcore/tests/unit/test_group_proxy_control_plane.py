"""
Regression test: pulpcore.app.models.Group is a proxy over django.contrib.auth.models.Group,
labeled "core.group". PulpDomainRouter._is_control_plane checked the proxy's own app_label
("core"), which isn't in CONTROL_PLANE_APPS -- only "auth" is -- so a Group created under
satellite ambient context was routed (and stayed) there instead of 'default', and
on_group_post_save (which only replicates when using == 'default') never propagated it anywhere.
"""

import uuid

import pytest
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Group

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    # Domain replication to the satellite is deferred via transaction.on_commit (see
    # domain_sync.on_domain_post_save), which never fires under pytest-django's test-wrapping
    # transaction unless explicitly flushed like this.
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"group-proxy-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/group-proxy-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestGroupProxyIsControlPlane:
    def test_group_created_in_satellite_context_lands_on_default(self, satellite_domain):
        with with_domain(satellite_domain):
            group = Group.objects.create(name=f"cp-group-{uuid.uuid4()}")
        try:
            assert group._state.db == "default"
            assert Group.objects.using("default").filter(pk=group.pk).exists()
            # Group IS instance-wide replicated to every satellite by rbac_sync (same as User/
            # Role) -- that's expected and separate from this fix. What this fix changes is that
            # 'default' -- not the satellite -- is where the Group actually lives and originates.
            assert Group.objects.using(SATELLITE_ALIAS).filter(pk=group.pk).exists()
        finally:
            Group.objects.using("default").filter(pk=group.pk).delete()
