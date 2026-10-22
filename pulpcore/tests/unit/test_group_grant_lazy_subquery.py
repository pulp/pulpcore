"""
Regression test: ObjectRolePermissionBackend built the group-membership filter as
`group_id__in=user_obj.groups.values_list("pk", flat=True)`, a lazy queryset. Passed into a
`GroupRole.objects.using(alias)` query, Django embeds it as a subquery executed against that same
connection instead of evaluating it against wherever `user_obj.groups` itself routes. `auth_user_
groups` membership rows are never replicated to satellites, so checking a group-based grant from
satellite-scoped context (or on a satellite-alias target) always found zero matching groups there,
even though the user really is a member. Materializing the pks with list(...) first forces the
membership lookup to run on its own, correctly-routed connection before it's embedded in the
GroupRole query.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Group
from pulpcore.app.models.role import Role
from pulpcore.app.rbac_sync import replicate_group, replicate_role, replicate_user
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
            name=f"group-grant-{uuid.uuid4().hex[:10]}",
            storage_class="pulpcore.app.models.storage.FileSystem",
            storage_settings={"location": "/tmp/group-grant-domain"},
            database_alias=SATELLITE_ALIAS,
        )
    yield domain
    domain.delete()


class TestGroupBasedDomainGrantOnSatellite:
    def test_has_perm_finds_domain_wide_group_grant_on_satellite(self, satellite_domain):
        user = User.objects.create(username=str(uuid.uuid4()))
        group = Group.objects.create(name=f"grp-{uuid.uuid4()}")
        user.groups.add(group)
        role = Role.objects.create(name=f"domain-viewer-{uuid.uuid4()}")
        role.permissions.set(
            [Permission.objects.get(content_type__app_label="core", codename="view_remote")]
        )
        replicate_user(user)
        replicate_group(group)
        replicate_role(role)
        try:
            # Domain-wide grants resolve explicitly to the domain's own alias -- the satellite.
            grant = assign_role(role.name, group, domain=satellite_domain)
            assert grant._state.db == SATELLITE_ALIAS

            # The membership row (auth_user_groups) only exists on 'default', where User/Group
            # live. The check below must still find it regardless of ambient context.
            assert user.has_perm("core.view_remote", satellite_domain)

            with with_domain(satellite_domain):
                assert user.has_perm("core.view_remote", satellite_domain)
        finally:
            role.delete()
            group.delete()
            user.delete()
