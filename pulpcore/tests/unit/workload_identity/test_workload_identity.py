import base64
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from rest_framework.exceptions import AuthenticationFailed

from pulpcore.app.access_policy import DefaultAccessPolicy
from pulpcore.app.checks import (
    workload_identity_domain_scopes,
    workload_identity_reserved_username,
    workload_identity_unqualified_name_scopes,
)
from pulpcore.app.models import Domain, Group, Repository
from pulpcore.app.models.role import Role
from pulpcore.app.role_util import get_objects_for_user
from pulpcore.app.util import get_prn
from pulpcore.app.workload_identity import config as wi_config
from pulpcore.app.workload_identity.authentication import WorkloadIdentityAuthentication
from pulpcore.app.workload_identity.authz import (
    _scope_matches,
    grants_queryset,
    has_grant_perm,
    permissions_for,
)
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


# --- domain fixtures ---


@pytest.fixture
def domain_a(db):
    return Domain.objects.create(
        name="tenant-a",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"base_path": "/foo"},
    )


@pytest.fixture
def domain_b(db):
    return Domain.objects.create(
        name="tenant-b",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"base_path": "/foo"},
    )


@pytest.fixture
def prod_in_a(domain_a):
    return Repository.objects.create(name="prod", pulp_domain=domain_a)


@pytest.fixture
def prod_in_b(domain_b):
    return Repository.objects.create(name="prod", pulp_domain=domain_b)


# --- domain scope ---


def test_has_grant_perm_domain_scope(repo_viewer_role, prod_in_a, prod_in_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "domain", "domain": "tenant-a"}}]
    assert has_grant_perm(grants, "core.view_repository", prod_in_a) is True
    assert has_grant_perm(grants, "core.view_repository", prod_in_b) is False


def test_grants_queryset_domain_scope(repo_viewer_role, prod_in_a, prod_in_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "domain", "domain": "tenant-a"}}]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.filter(name="prod"))
    assert set(qs.values_list("pulp_domain__name", flat=True)) == {"tenant-a"}


# --- object scope: domain-qualified name (tenant isolation) ---


def test_has_grant_perm_object_name_domain_qualified(repo_viewer_role, prod_in_a, prod_in_b):
    grants = [
        {"role": "repo_viewer", "scope": {"type": "object", "name": "prod", "domain": "tenant-a"}}
    ]
    assert has_grant_perm(grants, "core.view_repository", prod_in_a) is True
    assert has_grant_perm(grants, "core.view_repository", prod_in_b) is False


def test_grants_queryset_object_name_domain_qualified(repo_viewer_role, prod_in_a, prod_in_b):
    grants = [
        {"role": "repo_viewer", "scope": {"type": "object", "name": "prod", "domain": "tenant-a"}}
    ]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.filter(name="prod"))
    assert set(qs.values_list("pulp_domain__name", flat=True)) == {"tenant-a"}


def test_object_name_bare_matches_across_domains(repo_viewer_role, prod_in_a, prod_in_b):
    # Documents the unqualified behaviour the pulpcore.W008 check warns about.
    grants = [{"role": "repo_viewer", "scope": {"type": "object", "name": "prod"}}]
    assert has_grant_perm(grants, "core.view_repository", prod_in_a) is True
    assert has_grant_perm(grants, "core.view_repository", prod_in_b) is True


# --- object scope: prn ---


def test_has_grant_perm_prn_scope(repo_viewer_role, repo_a, repo_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "object", "prn": get_prn(repo_a)}}]
    assert has_grant_perm(grants, "core.view_repository", repo_a) is True
    assert has_grant_perm(grants, "core.view_repository", repo_b) is False


def test_grants_queryset_prn_scope(repo_viewer_role, repo_a, repo_b):
    grants = [{"role": "repo_viewer", "scope": {"type": "object", "prn": get_prn(repo_a)}}]
    qs = grants_queryset(grants, "core.view_repository", Repository.objects.all())
    assert set(qs.values_list("name", flat=True)) == {"repo-a"}


# --- principal surface ---


def test_principal_get_all_permissions_model_level(repo_viewer_role):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    assert principal.get_all_permissions() == {"core.view_repository"}


def test_principal_get_all_permissions_object_level(repo_viewer_role, repo_a):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    assert principal.get_all_permissions(repo_a) == {"view_repository"}


def test_principal_has_module_perms(repo_viewer_role):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    assert principal.has_module_perms("core") is True
    assert principal.has_module_perms("auth") is False


def test_principal_groups_default_empty(db):
    principal = WorkloadIdentityPrincipal([])
    assert principal.group_names == ()
    assert list(principal.groups) == []


def test_principal_groups_from_group_names(db):
    group = Group.objects.create(name="grp-a")
    principal = WorkloadIdentityPrincipal([])
    principal.group_names = ("grp-a",)
    assert list(principal.groups) == [group]


def test_principal_str():
    assert str(WorkloadIdentityPrincipal([])) == "workload-identity"
    assert str(WorkloadIdentityPrincipal([], username="ci")) == "ci"


# --- access_policy.get_user_group_values override ---


def test_get_user_group_values_principal_empty(db):
    assert DefaultAccessPolicy().get_user_group_values(WorkloadIdentityPrincipal([])) == []


def test_get_user_group_values_principal_reports_group_names(db):
    principal = WorkloadIdentityPrincipal([])
    principal.group_names = ("grp-a",)
    assert DefaultAccessPolicy().get_user_group_values(principal) == ["grp-a"]


def test_get_user_group_values_real_user_fallthrough(db):
    user = get_user_model().objects.create(username="alice")
    user.groups.add(Group.objects.create(name="grp-a"))
    assert DefaultAccessPolicy().get_user_group_values(user) == ["grp-a"]


# --- authentication._get_token gating ---


class _FakeRequest:
    def __init__(self, authorization):
        self.META = {"HTTP_AUTHORIZATION": authorization} if authorization else {}


def _basic(username, password):
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


def test_get_token_bearer():
    auth = WorkloadIdentityAuthentication()
    assert auth._get_token(_FakeRequest("Bearer abc.def.ghi")) == "abc.def.ghi"


def test_get_token_basic_reserved_username():
    auth = WorkloadIdentityAuthentication()
    assert auth._get_token(_FakeRequest(_basic("__token__", "the-token"))) == "the-token"


def test_get_token_basic_wrong_username_falls_through():
    auth = WorkloadIdentityAuthentication()
    assert auth._get_token(_FakeRequest(_basic("someuser", "the-token"))) is None


def test_get_token_basic_no_colon():
    auth = WorkloadIdentityAuthentication()
    value = base64.b64encode(b"nocolon").decode()
    assert auth._get_token(_FakeRequest("Basic " + value)) is None


def test_get_token_malformed_header():
    auth = WorkloadIdentityAuthentication()
    assert auth._get_token(_FakeRequest("Bearer")) is None
    assert auth._get_token(_FakeRequest("")) is None


# --- config helpers ---


@override_settings(WORKLOAD_IDENTITY={"providers": {"p": {"issuer": "https://issuer"}}})
def test_config_provider_for_issuer():
    assert wi_config.provider_for_issuer("https://issuer") == {"issuer": "https://issuer"}
    assert wi_config.provider_for_issuer("https://other") is None


@override_settings(WORKLOAD_IDENTITY={})
def test_config_basic_username_default():
    assert wi_config.basic_username() == "__token__"


@override_settings(WORKLOAD_IDENTITY={"basic_auth_username": "ci-bot"})
def test_config_basic_username_override():
    assert wi_config.basic_username() == "ci-bot"


@override_settings(WORKLOAD_IDENTITY={})
def test_config_strategy_default():
    assert wi_config.strategy() == "union"


# --- deploy checks W006 / W007 / W008 ---


@override_settings(WORKLOAD_IDENTITY={"basic_auth_username": "ci-bot"})
def test_check_reserved_username_collision(db):
    get_user_model().objects.create(username="ci-bot")
    assert "pulpcore.W006" in [m.id for m in workload_identity_reserved_username(None)]


@override_settings(WORKLOAD_IDENTITY={"basic_auth_username": "ci-bot"})
def test_check_reserved_username_no_collision(db):
    assert workload_identity_reserved_username(None) == []


@override_settings(
    DOMAIN_ENABLED=False,
    WORKLOAD_IDENTITY={
        "providers": {
            "p": {
                "rules": [{"grants": [{"role": "r", "scope": {"type": "domain", "domain": "d"}}]}]
            }
        }
    },
)
def test_check_domain_scope_while_domains_off():
    assert "pulpcore.W007" in [m.id for m in workload_identity_domain_scopes(None)]


@override_settings(
    DOMAIN_ENABLED=True,
    WORKLOAD_IDENTITY={
        "providers": {
            "p": {
                "rules": [{"grants": [{"role": "r", "scope": {"type": "object", "name": "prod"}}]}]
            }
        }
    },
)
def test_check_unqualified_name_scope_while_domains_on():
    assert "pulpcore.W008" in [m.id for m in workload_identity_unqualified_name_scopes(None)]


@override_settings(
    DOMAIN_ENABLED=True,
    WORKLOAD_IDENTITY={
        "providers": {
            "p": {
                "rules": [
                    {
                        "grants": [
                            {
                                "role": "r",
                                "scope": {"type": "object", "name": "prod", "domain": "d"},
                            }
                        ]
                    }
                ]
            }
        }
    },
)
def test_check_qualified_name_scope_no_warning():
    assert workload_identity_unqualified_name_scopes(None) == []


# --- authz: remaining branches ---


def test_scope_matches_global_obj_none():
    assert _scope_matches({"type": "global"}, None) is True


def test_scope_matches_object_obj_none():
    assert _scope_matches({"type": "object", "name": "x"}, None) is False


def test_scope_matches_domain_on_domain_object(domain_a):
    assert _scope_matches({"type": "domain", "domain": "tenant-a"}, domain_a) is True
    assert _scope_matches({"type": "domain", "domain": "other"}, domain_a) is False


def test_has_grant_perm_empty_role(db, repo_a):
    grants = [{"role": "", "scope": {"type": "global"}}]
    assert has_grant_perm(grants, "core.view_repository", repo_a) is False


# --- get_objects_for_user: list-of-perms paths ---


def test_get_objects_for_user_any_perm(repo_viewer_role, repo_a, repo_b):
    principal = WorkloadIdentityPrincipal(
        [{"role": "repo_viewer", "scope": {"type": "object", "name": "repo-a"}}]
    )
    qs = get_objects_for_user(
        principal,
        ["core.view_repository", "core.change_repository"],
        Repository.objects.all(),
        any_perm=True,
    )
    assert set(qs.values_list("name", flat=True)) == {"repo-a"}


def test_get_objects_for_user_all_perms_intersection(repo_viewer_role, repo_a):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    qs = get_objects_for_user(
        principal,
        ["core.view_repository", "core.change_repository"],
        Repository.objects.all(),
    )
    # AND of a granted (view) and a non-granted (change) permission -> empty.
    assert qs.count() == 0


# --- principal: remaining surface ---


def test_principal_has_perms(repo_viewer_role, repo_a):
    principal = WorkloadIdentityPrincipal([{"role": "repo_viewer", "scope": {"type": "global"}}])
    assert principal.has_perms(["core.view_repository"], repo_a) is True
    assert principal.has_perms(["core.view_repository", "core.change_repository"], repo_a) is False


def test_principal_get_group_permissions(db):
    assert WorkloadIdentityPrincipal([]).get_group_permissions() == set()


# --- authentication: _get_token edge + header ---


def test_get_token_basic_non_utf8():
    value = base64.b64encode(b"\xff\xfe").decode()
    assert WorkloadIdentityAuthentication()._get_token(_FakeRequest("Basic " + value)) is None


def test_authenticate_header():
    assert WorkloadIdentityAuthentication().authenticate_header(_FakeRequest("")) == "Bearer"


# --- authentication.authenticate: full JWT validation (RSA key + mocked JWKS) ---


_ISSUER = "https://issuer"
WI_AUTH = {
    "providers": {
        "p": {
            "issuer": _ISSUER,
            "jwks_url": "https://issuer/jwks",
            "audience": "pulp",
            "algorithms": ["RS256"],
            "rules": [
                {
                    "match": {"repository": "org/app"},
                    "grants": [{"role": "r", "scope": {"type": "global"}}],
                }
            ],
        }
    }
}


def _private_pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture(scope="module")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _private_pem(key), public_pem


@pytest.fixture
def mock_jwks(rsa_keys, monkeypatch):
    _, public_pem = rsa_keys
    fake = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_pem))
    monkeypatch.setattr(wi_config, "jwks_client", lambda provider: fake)


def _token(private_pem, **overrides):
    now = int(time.time())
    claims = {"iss": _ISSUER, "aud": "pulp", "iat": now, "exp": now + 300, "repository": "org/app"}
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


def _bearer(token):
    return _FakeRequest(f"Bearer {token}")


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_valid_token(rsa_keys, mock_jwks):
    private_pem, _ = rsa_keys
    principal, claims = WorkloadIdentityAuthentication().authenticate(_bearer(_token(private_pem)))
    assert isinstance(principal, WorkloadIdentityPrincipal)
    assert claims["repository"] == "org/app"
    assert principal.grants == [{"role": "r", "scope": {"type": "global"}}]


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_bad_signature(rsa_keys, mock_jwks):
    other_pem = _private_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    with pytest.raises(AuthenticationFailed):
        WorkloadIdentityAuthentication().authenticate(_bearer(_token(other_pem)))


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_wrong_audience(rsa_keys, mock_jwks):
    private_pem, _ = rsa_keys
    with pytest.raises(AuthenticationFailed):
        WorkloadIdentityAuthentication().authenticate(_bearer(_token(private_pem, aud="wrong")))


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_expired(rsa_keys, mock_jwks):
    private_pem, _ = rsa_keys
    now = int(time.time())
    with pytest.raises(AuthenticationFailed):
        token = _token(private_pem, exp=now - 10, iat=now - 20)
        WorkloadIdentityAuthentication().authenticate(_bearer(token))


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_unknown_issuer_returns_none(rsa_keys):
    private_pem, _ = rsa_keys
    request = _bearer(_token(private_pem, iss="https://evil"))
    assert WorkloadIdentityAuthentication().authenticate(request) is None


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_no_matching_rule(rsa_keys, mock_jwks):
    private_pem, _ = rsa_keys
    with pytest.raises(AuthenticationFailed):
        WorkloadIdentityAuthentication().authenticate(
            _bearer(_token(private_pem, repository="other/x"))
        )


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_not_a_jwt_returns_none():
    assert WorkloadIdentityAuthentication().authenticate(_bearer("not-a-jwt")) is None


@override_settings(WORKLOAD_IDENTITY=WI_AUTH)
def test_authenticate_no_token_returns_none():
    assert WorkloadIdentityAuthentication().authenticate(_FakeRequest("")) is None
