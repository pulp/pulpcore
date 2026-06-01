import pytest
from django.apps import apps

from pulpcore.app.apps import adjust_roles
from pulpcore.app.models.role import Role

ROLE_PREFIX = "core."
VIEW_REPO_PERM = "core.view_repository"
CHANGE_REPO_PERM = "core.change_repository"


@pytest.fixture(autouse=True)
def _cleanup_test_roles(db):
    yield
    Role.objects.filter(name__startswith=ROLE_PREFIX + "test_").delete()


def test_creates_new_locked_role(db):
    desired = {
        "core.test_viewer": {
            "description": "Can view repositories",
            "permissions": [VIEW_REPO_PERM],
        }
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    role = Role.objects.get(name="core.test_viewer")
    assert role.locked is True
    assert role.description == "Can view repositories"
    assert role.permissions.filter(codename="view_repository").exists()


def test_updates_unlocked_role_to_locked(db):
    """Core scenario from AAP-73644: a role pre-created with locked=False
    must be updated to locked=True instead of raising UniqueViolation."""
    Role.objects.create(name="core.test_viewer", locked=False)

    desired = {
        "core.test_viewer": {
            "description": "Can view repositories",
            "permissions": [VIEW_REPO_PERM],
        }
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    role = Role.objects.get(name="core.test_viewer")
    assert role.locked is True
    assert role.description == "Can view repositories"


def test_idempotent(db):
    desired = {
        "core.test_viewer": {
            "description": "Can view repositories",
            "permissions": [VIEW_REPO_PERM],
        }
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    assert Role.objects.filter(name="core.test_viewer").count() == 1
    role = Role.objects.get(name="core.test_viewer")
    assert role.locked is True
    assert role.description == "Can view repositories"


def test_updates_description(db):
    Role.objects.create(name="core.test_viewer", locked=True, description="Old description")

    desired = {
        "core.test_viewer": {
            "description": "New description",
            "permissions": [VIEW_REPO_PERM],
        }
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    role = Role.objects.get(name="core.test_viewer")
    assert role.description == "New description"


def test_removes_obsolete_locked_roles(db):
    Role.objects.create(name="core.test_obsolete", locked=True)

    desired = {
        "core.test_viewer": [VIEW_REPO_PERM],
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    assert not Role.objects.filter(name="core.test_obsolete").exists()
    assert Role.objects.filter(name="core.test_viewer").exists()


def test_preserves_unlocked_roles_on_cleanup(db):
    Role.objects.create(name="core.test_custom", locked=False)

    desired = {
        "core.test_viewer": [VIEW_REPO_PERM],
    }
    adjust_roles(apps, ROLE_PREFIX, desired, verbosity=0)

    assert Role.objects.filter(name="core.test_custom").exists()
