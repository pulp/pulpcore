"""
Regression test: ObjectRolePermissionBackend checked global grants (no object, no domain) via
user_obj.object_roles.filter(...) -- a reverse-FK related manager, which passes user_obj as an
instance hint to PulpDomainRouter. The router gives a persisted instance's own db priority over
ambient context, and User is control-plane (always 'default'), so this query always resolved to
'default' regardless of where the check is actually happening. role_util.assign_role creates a
global grant via ambient routing instead (it lands wherever the request creating it was already
scoped), so a grant created from satellite-domain context was invisible to has_perm/
get_all_permissions checked from that same context, while GroupRole.objects (a plain manager,
genuinely ambient) worked correctly. Querying UserRole directly, like GroupRole, fixes the split.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain
from pulpcore.app.models.role import Role
from pulpcore.app.rbac_sync import replicate_role, replicate_user
from pulpcore.app.role_util import assign_role

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

User = get_user_model()

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    # Domain replication to the satellite is deferred via transaction.on_commit (see
    # domain_sync.on_domain_post_save), which never fires under pytest-django's test-wrapping
    # transaction unless explicitly flushed like this.
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=f"global-grant-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/global-grant-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestGlobalUserGrantFollowsAmbientContext:
    def test_has_perm_finds_grant_created_under_satellite_context(self, satellite_domain):
        user = User.objects.create(username=str(uuid.uuid4()))
        role = Role.objects.create(name=f"global-viewer-{uuid.uuid4()}")
        role.permissions.set(
            [Permission.objects.get(content_type__app_label="core", codename="view_remote")]
        )
        replicate_user(user)
        replicate_role(role)
        try:
            # A grant tied to neither object nor domain lands wherever the request creating it
            # was ambiently scoped (role_util.assign_role) -- here, the satellite.
            with with_domain(satellite_domain):
                grant = assign_role(role.name, user)
            assert grant._state.db == SATELLITE_ALIAS

            # Checking it back from the SAME ambient context must find it.
            with with_domain(satellite_domain):
                assert user.has_perm("core.view_remote")
                assert "core.view_remote" in user.get_all_permissions()

            # And it must NOT be visible from 'default' ambient context -- it only exists on
            # the satellite, consistent with role_util.get_objects_for_user_roles reading each
            # grant kind back from qs's own alias only.
            assert not user.has_perm("core.view_remote")
        finally:
            role.delete()
            user.delete()
