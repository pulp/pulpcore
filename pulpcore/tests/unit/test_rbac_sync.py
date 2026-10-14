from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from pulpcore.app.contexts import with_domain
from pulpcore.app.models import Domain, Group, Repository
from pulpcore.app.models.role import Role, UserRole
from pulpcore.app.rbac_sync import (
    ensure_replicated_on_alias,
    remove_replicated_group,
    remove_replicated_role,
    remove_replicated_user,
    replicate_group,
    replicate_role,
    replicate_user,
)
from pulpcore.app.role_util import assign_role, get_objects_for_user, remove_role

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

User = get_user_model()

pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


def _replicated_permission_ids(replica, alias):
    # replica.permissions.filter(...)/.exists() can't be trusted here: Permission is
    # control-plane, so that M2M manager always queries 'default' regardless of replica's own
    # alias (see rbac_sync._set_permissions_on_alias). Read the through table directly instead.
    field = type(replica)._meta.get_field("permissions")
    through = field.remote_field.through
    source_id = f"{field.m2m_field_name()}_id"
    target_id = f"{field.m2m_reverse_field_name()}_id"
    return set(
        through.objects.using(alias)
        .filter(**{source_id: replica.pk})
        .values_list(target_id, flat=True)
    )


@pytest.fixture
def satellite_domain():
    domain = Domain.objects.create(
        name="rbac-sync-test-domain",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/rbac-sync-test-domain"},
        database_alias=SATELLITE_ALIAS,
    )
    yield domain
    domain.delete()


@pytest.fixture
def satellite_repository(satellite_domain):
    with with_domain(satellite_domain):
        repo = Repository.objects.create(name=str(uuid4()), pulp_domain=satellite_domain)
    yield repo
    Repository.objects.using(SATELLITE_ALIAS).filter(pk=repo.pk).delete()


@pytest.fixture
def viewer_role():
    role = Role.objects.create(name=f"rbac-sync-viewer-{uuid4()}")
    role.permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="view_repository")
    )
    yield role
    remove_replicated_role(role)
    role.delete()


@pytest.fixture
def user():
    u = User.objects.create(username=str(uuid4()))
    yield u
    remove_replicated_user(u)
    u.delete()


@pytest.fixture
def group(user):
    g = Group.objects.create(name=str(uuid4()))
    g.user_set.add(user)
    yield g
    remove_replicated_group(g)
    g.delete()


class TestReplicateIdentities:
    def test_user_replicates_to_satellite(self, user):
        replicate_user(user)
        replica = User.objects.using(SATELLITE_ALIAS).get(pk=user.pk)
        assert replica.username == user.username

    def test_group_replicates_with_permissions(self, group, viewer_role):
        perm = Permission.objects.get(content_type__app_label="core", codename="view_repository")
        group.permissions.add(perm)
        replicate_group(group)
        replica = Group.objects.using(SATELLITE_ALIAS).get(pk=group.pk)
        assert replica.name == group.name
        assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == {perm.pk}

    def test_role_replicates_with_permissions(self, viewer_role):
        perm = Permission.objects.get(content_type__app_label="core", codename="view_repository")
        replicate_role(viewer_role)
        replica = Role.objects.using(SATELLITE_ALIAS).get(pulp_id=viewer_role.pulp_id)
        assert replica.name == viewer_role.name
        assert _replicated_permission_ids(replica, SATELLITE_ALIAS) == {perm.pk}

    def test_ensure_replicated_on_alias_backfills_everything(self, user, group, viewer_role):
        # The post_save signals already replicated these eagerly on creation -- delete the
        # satellite-side copies to simulate a satellite that missed out (e.g. it didn't exist yet
        # when these were created), then verify the backfill repairs it.
        User.objects.using(SATELLITE_ALIAS).filter(pk=user.pk).delete()
        Group.objects.using(SATELLITE_ALIAS).filter(pk=group.pk).delete()
        Role.objects.using(SATELLITE_ALIAS).filter(pulp_id=viewer_role.pulp_id).delete()

        ensure_replicated_on_alias(SATELLITE_ALIAS)

        assert User.objects.using(SATELLITE_ALIAS).filter(pk=user.pk).exists()
        assert Group.objects.using(SATELLITE_ALIAS).filter(pk=group.pk).exists()
        assert Role.objects.using(SATELLITE_ALIAS).filter(pulp_id=viewer_role.pulp_id).exists()


class TestGrantRouting:
    def test_object_level_grant_lives_only_on_target_alias(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)

        with with_domain(satellite_domain):
            grant = assign_role(viewer_role.name, user, satellite_repository)

        assert grant._state.db == SATELLITE_ALIAS
        assert UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()
        assert not UserRole.objects.using("default").filter(pk=grant.pk).exists()

        with with_domain(satellite_domain):
            remove_role(viewer_role.name, user, satellite_repository)

    def test_domain_wide_grant_is_created_directly_on_domains_alias(
        self, user, viewer_role, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)

        # No with_domain() here on purpose: a domain-wide grant is resolved explicitly from the
        # domain argument (see role_util.assign_role), not trusted from ambient context, so this
        # must land on the satellite even though ambient context is 'default'.
        grant = assign_role(viewer_role.name, user, domain=satellite_domain)

        assert grant._state.db == SATELLITE_ALIAS
        assert UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()
        assert not UserRole.objects.using("default").filter(pk=grant.pk).exists()

        remove_role(viewer_role.name, user, domain=satellite_domain)

    def test_global_grant_follows_ambient_context(self, user, viewer_role, satellite_domain):
        replicate_user(user)
        replicate_role(viewer_role)

        # A grant with neither obj nor domain set isn't resolved explicitly -- it just trusts
        # ambient context, same as an object-level grant, so it lands on the satellite here.
        with with_domain(satellite_domain):
            grant = assign_role(viewer_role.name, user)

        assert grant._state.db == SATELLITE_ALIAS
        assert UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()
        assert not UserRole.objects.using("default").filter(pk=grant.pk).exists()

        with with_domain(satellite_domain):
            remove_role(viewer_role.name, user)


class TestNativeCascadeReplacesCustomCleanup:
    def test_deleting_target_object_cascades_to_local_grant(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        # This is the whole point of the redesign: once User/Role are mirrored and the grant is a
        # real local row on the object's own alias, Django's native GenericRelation cascade
        # (BaseModel.user_roles, unmodified upstream) cleans it up automatically -- no custom
        # cross-plane signal needed.
        replicate_user(user)
        replicate_role(viewer_role)
        with with_domain(satellite_domain):
            grant = assign_role(viewer_role.name, user, satellite_repository)
        assert UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()

        Repository.objects.using(SATELLITE_ALIAS).filter(pk=satellite_repository.pk).delete()

        assert not UserRole.objects.using(SATELLITE_ALIAS).filter(pk=grant.pk).exists()


class TestReadPathQueriesLocalAlias:
    def test_get_objects_for_user_sees_object_level_grant(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)
        with with_domain(satellite_domain):
            assign_role(viewer_role.name, user, satellite_repository)

            qs = get_objects_for_user(
                user,
                "core.view_repository",
                Repository.objects.filter(pulp_domain=satellite_domain),
            )
            assert qs.db == SATELLITE_ALIAS
            assert set(qs.values_list("pk", flat=True)) == {satellite_repository.pk}

            remove_role(viewer_role.name, user, satellite_repository)

    def test_get_objects_for_user_sees_domain_wide_grant(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)
        # Created directly on the domain's own alias -- no replication involved.
        assign_role(viewer_role.name, user, domain=satellite_domain)

        with with_domain(satellite_domain):
            qs = get_objects_for_user(
                user,
                "core.view_repository",
                Repository.objects.filter(pulp_domain=satellite_domain),
            )
            assert set(qs.values_list("pk", flat=True)) == {satellite_repository.pk}

        remove_role(viewer_role.name, user, domain=satellite_domain)

    def test_get_objects_for_user_sees_global_grant_from_same_alias(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)
        # Created under the satellite's own ambient context, so it's only visible to a queryset
        # pinned to that same alias -- not a global, instance-wide grant.
        with with_domain(satellite_domain):
            grant = assign_role(viewer_role.name, user)
        assert grant._state.db == SATELLITE_ALIAS

        with with_domain(satellite_domain):
            qs = get_objects_for_user(
                user,
                "core.view_repository",
                Repository.objects.filter(pulp_domain=satellite_domain),
            )
            assert set(qs.values_list("pk", flat=True)) == {satellite_repository.pk}

            remove_role(viewer_role.name, user)

    def test_global_grant_on_default_does_not_reach_satellite(
        self, user, viewer_role, satellite_repository, satellite_domain
    ):
        replicate_user(user)
        replicate_role(viewer_role)
        # Granted with ambient context left on 'default' -- this is the scoping tradeoff of
        # dropping true instance-wide global grants: a satellite needs its own grant.
        grant = assign_role(viewer_role.name, user)
        assert grant._state.db == "default"

        with with_domain(satellite_domain):
            qs = get_objects_for_user(
                user,
                "core.view_repository",
                Repository.objects.filter(pulp_domain=satellite_domain),
            )
            assert qs.count() == 0

        remove_role(viewer_role.name, user)

    def test_no_grant_means_no_access(self, user, satellite_repository, satellite_domain):
        with with_domain(satellite_domain):
            qs = get_objects_for_user(
                user,
                "core.view_repository",
                Repository.objects.filter(pulp_domain=satellite_domain),
            )
            assert qs.count() == 0
