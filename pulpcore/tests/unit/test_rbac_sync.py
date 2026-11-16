from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from pulpcore.app.models import Domain, Group
from pulpcore.app.models.role import GroupRole, Role, UserRole
from pulpcore.app.rbac_sync import ensure_identities_on_alias
from pulpcore.app.role_util import assign_role

from .test_multi_database_routing import SATELLITE_ALIAS, requires_multi_db

User = get_user_model()
pytestmark = [requires_multi_db, pytest.mark.django_db(databases=["default", SATELLITE_ALIAS])]


@pytest.fixture
def satellite_domain():
    with TestCase.captureOnCommitCallbacks(execute=True):
        domain = Domain.objects.create(
            name=str(uuid4()),
            storage_class="pulpcore.app.models.storage.FileSystem",
            database_alias=SATELLITE_ALIAS,
        )
    yield domain


def _satellite_role():
    return Role.objects.using(SATELLITE_ALIAS).get(name="core.task_viewer")


def test_identities_are_not_copied_until_granted():
    user = User.objects.create(username=str(uuid4()), password="secret")
    group = Group.objects.create(name=str(uuid4()))
    assert not User.objects.using(SATELLITE_ALIAS).filter(pk=user.pk).exists()
    assert not Group.objects.using(SATELLITE_ALIAS).filter(pk=group.pk).exists()


@pytest.mark.parametrize("group_grant", [False, True])
def test_grant_creates_stub_without_credentials(satellite_domain, group_grant):
    user = User.objects.create(username=str(uuid4()), password="secret")
    group = Group.objects.create(name=str(uuid4()))
    entity = group if group_grant else user
    assign_role(_satellite_role().name, entity, domain=satellite_domain)

    model = Group if group_grant else User
    stub = model.objects.using(SATELLITE_ALIAS).get(pk=entity.pk)
    if group_grant:
        assert stub.name == f"pulp-{group.pk}"
    else:
        assert stub.username == f"pulp-{user.pk}"
        assert not stub.has_usable_password()


def test_stub_never_collides_with_reused_username(satellite_domain):
    name = str(uuid4())
    old = User.objects.create(username=name)
    assign_role(_satellite_role().name, old, domain=satellite_domain)
    old.delete()  # Satellite cleanup deliberately not executed: simulate a failed removal.
    new = User.objects.create(username=name)
    assign_role(_satellite_role().name, new, domain=satellite_domain)
    assert UserRole.objects.using(SATELLITE_ALIAS).filter(user_id=new.pk).exists()


def test_ensure_identities_is_idempotent():
    user = User.objects.create(username=str(uuid4()))
    ensure_identities_on_alias(SATELLITE_ALIAS, user_ids=[user.pk])
    ensure_identities_on_alias(SATELLITE_ALIAS, user_ids=[user.pk])
    ensure_identities_on_alias("default", user_ids=[user.pk])
    assert User.objects.using(SATELLITE_ALIAS).filter(pk=user.pk).count() == 1


@pytest.mark.parametrize("model", [User, Group])
def test_delete_removes_stub_and_grants_after_commit(satellite_domain, model):
    field = "username" if model is User else "name"
    entity = model.objects.create(**{field: str(uuid4())})
    assign_role(_satellite_role().name, entity, domain=satellite_domain)
    pk = entity.pk
    grants = UserRole if model is User else GroupRole
    grant_field = "user_id" if model is User else "group_id"
    with TestCase.captureOnCommitCallbacks(execute=True):
        entity.delete()
        assert model.objects.using(SATELLITE_ALIAS).filter(pk=pk).exists()
    assert not model.objects.using(SATELLITE_ALIAS).filter(pk=pk).exists()
    assert not grants.objects.using(SATELLITE_ALIAS).filter(**{grant_field: pk}).exists()


def test_delete_rollback_preserves_stub():
    user = User.objects.create(username=str(uuid4()))
    ensure_identities_on_alias(SATELLITE_ALIAS, user_ids=[user.pk])
    with pytest.raises(RuntimeError), TestCase.captureOnCommitCallbacks(execute=True):
        with transaction.atomic(using="default"):
            User.objects.get(pk=user.pk).delete()
            raise RuntimeError("rollback")
    assert User.objects.using(SATELLITE_ALIAS).filter(pk=user.pk).exists()
