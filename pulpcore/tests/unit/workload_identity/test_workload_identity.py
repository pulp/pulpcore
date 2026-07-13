import pytest
from django.contrib.auth.models import Permission
from django.test import override_settings

from pulpcore.app.models import Repository
from pulpcore.app.models.role import Role
from pulpcore.app.role_util import get_objects_for_user

from pulpcore.app.workload_identity.authz import grants_queryset, has_grant_perm, permissions_for
from pulpcore.app.workload_identity.principal import WorkloadIdentityPrincipal
from pulpcore.app.workload_identity.rules import grants_for


PROVIDER = {
    "issuer": "https://issuer",
    "rules": [
        {
            "match": {"repository": "org/infra", "ref": "refs/heads/main"},
            "grants": [{"role": "role1", "scope": {"type": "global"}}],
        },
        {
            "match": {"repository": "org/*"},
            "grants": [{"role": "role2", "scope": {"type": "domain", "domain": "default"}}],
        },
    ],
}


# --- rules.grants_for (no database) ---


def test_rules_no_match():
    assert grants_for(PROVIDER, {"repository": "other/x"}) == []


@override_settings(WORKLOAD_IDENTITY={"strategy": "union"})
def test_rules_union_accumulates():
    grants = grants_for(PROVIDER, {"repository": "org/infra", "ref": "refs/heads/main"})
    assert {g["role"] for g in grants} == {"role1", "role2"}


@override_settings(WORKLOAD_IDENTITY={"strategy": "first-match"})
def test_rules_first_match_stops():
    grants = grants_for(PROVIDER, {"repository": "org/infra", "ref": "refs/heads/main"})
    assert [g["role"] for g in grants] == ["role1"]


def test_rules_glob_only():
    grants = grants_for(PROVIDER, {"repository": "org/app"})
    assert [g["role"] for g in grants] == ["role2"]


# --- database fixtures ---


@pytest.fixture
def repo_viewer_role(db):
    role = Role.objects.create(name="repo_viewer")
    role.permissions.add(
        Permission.objects.get(content_type__app_label="core", codename="view_repository")
    )
    return role


@pytest.fixture
def repo_a(db):
    return Repository.objects.create(name="repo-a")


@pytest.fixture
def repo_b(db):
    return Repository.objects.create(name="repo-b")


# --- authz.has_grant_perm ---


def test_has_grant_perm_global(repo_viewer_role, repo_a):
    grants = [{"role": "repo_viewer", "scope": {"type": "global"}}]
    assert has_grant_perm(grants, "core.view_repository", repo_a) is True


def test_has_grant_perm_object_scope(repo_viewer_role, repo_a, repo_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "object", "name": "repo-a"}}]
    assert has_grant_perm(grants, "core.view_repository", repo_a) is True
    assert has_grant_perm(grants, "core.view_repository", repo_b) is False


def test_has_grant_perm_wrong_permission(repo_viewer_role, repo_a):
    grants = [{"role": "repo_viewer", "scope": {"type": "global"}}]
    assert has_grant_perm(grants, "core.change_repository", repo_a) is False


def test_has_grant_perm_missing_role(db, repo_a):
    grants = [{"role": "does_not_exist", "scope": {"type": "global"}}]
    assert has_grant_perm(grants, "core.view_repository", repo_a) is False


# --- authz.permissions_for ---


def test_permissions_for(repo_viewer_role):
    grants = [{"role": "repo_viewer", "scope": {"type": "global"}}]
    assert "core.view_repository" in permissions_for(grants)


# --- authz.grants_queryset ---


def test_grants_queryset_global(repo_viewer_role, repo_a, repo_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "global"}}]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.all())
    assert {"repo-a", "repo-b"} <= set(qs.values_list("name", flat=True))


def test_grants_queryset_object(repo_viewer_role, repo_a, repo_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "object", "name": "repo-a"}}]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.all())
    assert set(qs.values_list("name", flat=True)) == {"repo-a"}


def test_grants_queryset_no_relevant_grant(db, repo_a):
    grants = [{"role": "does_not_exist", "scope": {"type": "global"}}]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.all())
    assert qs.count() == 0


# --- principal + get_objects_for_user branch ---


def test_principal_is_authenticated_and_has_perm(repo_viewer_role, repo_a):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    assert principal.is_authenticated is True
    assert principal.pk is None
    assert principal.has_perm("core.view_repository", repo_a) is True


def test_get_objects_for_user_scopes_by_grants(repo_viewer_role, repo_a, repo_b):
    principal = WorkloadIdentityPrincipal(
        [{"role": "repo_viewer", "scope": {"type": "object", "name": "repo-a"}}]
    )
    qs = get_objects_for_user(principal, "core.view_repository", Repository.objects.all())
    assert set(qs.values_list("name", flat=True)) == {"repo-a"}
