import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from pulpcore.app.apps import _populate_content_owner_roles
from pulpcore.app.models.role import Role


@pytest.mark.django_db
def test_populate_creates_owner_role_and_manage_roles_perm():
    from pulp_file.app.models import FileContent

    _populate_content_owner_roles(sender=FileContent._meta.app_config)

    ctype = ContentType.objects.get_for_model(FileContent, for_concrete_model=False)
    assert Permission.objects.filter(
        content_type=ctype, codename="manage_roles_filecontent"
    ).exists()

    role = Role.objects.get(name="file.filecontent_owner")
    assert role.locked is True
    codenames = set(role.permissions.values_list("codename", flat=True))
    assert codenames == {
        "view_filecontent",
        "change_filecontent",
        "delete_filecontent",
        "manage_roles_filecontent",
    }

    viewer = Role.objects.get(name="file.filecontent_viewer")
    assert viewer.locked is True
    assert set(viewer.permissions.values_list("codename", flat=True)) == {"view_filecontent"}


@pytest.mark.django_db
def test_assign_content_viewer_role_grants_view_only(monkeypatch):
    from django.contrib.auth import get_user_model
    from pulp_file.app.models import FileContent
    from pulpcore.app import role_util
    from pulpcore.app.role_util import assign_content_viewer_role, get_objects_for_user

    _populate_content_owner_roles(sender=FileContent._meta.app_config)

    user = get_user_model().objects.create(username="dedup_uploader")
    monkeypatch.setattr(role_util, "get_current_authenticated_user", lambda: user)

    content = FileContent.objects.create(relative_path="c.txt", digest="4" * 64)
    assign_content_viewer_role(content)

    qs = FileContent.objects.all()
    assert content in get_objects_for_user(user, "file.view_filecontent", qs, with_superuser=False)
    # View only: no change/delete/manage_roles on the deduplicated content unit.
    for perm in ("change_filecontent", "delete_filecontent", "manage_roles_filecontent"):
        assert not user.has_perm(f"file.{perm}", content)


@pytest.mark.django_db
def test_assign_content_owner_role_grants_current_user(monkeypatch):
    from django.contrib.auth import get_user_model
    from pulp_file.app.models import FileContent
    from pulpcore.app import role_util
    from pulpcore.app.role_util import assign_content_owner_role, get_objects_for_user

    _populate_content_owner_roles(sender=FileContent._meta.app_config)

    user = get_user_model().objects.create(username="uploader")
    monkeypatch.setattr(role_util, "get_current_authenticated_user", lambda: user)

    content = FileContent.objects.create(relative_path="a.txt", digest="0" * 64)
    assign_content_owner_role(content)

    visible = get_objects_for_user(
        user, "file.view_filecontent", FileContent.objects.all(), with_superuser=False
    )
    assert content in visible


@pytest.mark.django_db
def test_assign_content_owner_role_noop_without_user(monkeypatch):
    from pulp_file.app.models import FileContent
    from pulpcore.app import role_util
    from pulpcore.app.role_util import assign_content_owner_role

    _populate_content_owner_roles(sender=FileContent._meta.app_config)
    monkeypatch.setattr(role_util, "get_current_authenticated_user", lambda: None)

    content = FileContent.objects.create(relative_path="b.txt", digest="1" * 64)
    assign_content_owner_role(content)  # must not raise
    assert content.user_roles.count() == 0


@pytest.mark.django_db
def test_scope_queryset_includes_owned_orphan_content(monkeypatch):
    from types import SimpleNamespace
    from django.contrib.auth import get_user_model
    from pulp_file.app.models import FileContent
    from pulp_file.app.viewsets import FileContentViewSet
    from pulpcore.app import role_util
    from pulpcore.app.role_util import assign_content_owner_role
    from pulpcore.app.util import get_default_domain

    _populate_content_owner_roles(sender=FileContent._meta.app_config)
    user = get_user_model().objects.create(username="owner2")
    monkeypatch.setattr(role_util, "get_current_authenticated_user", lambda: user)

    owned = FileContent.objects.create(relative_path="owned.txt", digest="2" * 64)
    other = FileContent.objects.create(relative_path="other.txt", digest="3" * 64)
    assign_content_owner_role(owned)  # not in any repository

    view = FileContentViewSet()
    view.request = SimpleNamespace(user=user, pulp_domain=get_default_domain())
    scoped = view.scope_queryset(FileContent.objects.all())

    assert owned in scoped
    assert other not in scoped
