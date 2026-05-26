from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

User = get_user_model()


@pytest.mark.django_db
def test_creates_new_admin_with_password():
    out = StringIO()
    call_command("reset-admin-password", password="testpass123", stdout=out)
    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password("testpass123")
    assert "Successfully set password" in out.getvalue()


@pytest.mark.django_db
def test_resets_password_on_existing_superuser():
    User.objects.create_user(username="admin", password="old", is_superuser=True, is_staff=True)
    out = StringIO()
    call_command("reset-admin-password", password="newpass", stdout=out)
    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password("newpass")


@pytest.mark.django_db
def test_promotes_existing_non_superuser_admin():
    User.objects.create_user(username="admin", password="old", is_superuser=False, is_staff=False)
    out = StringIO()
    call_command("reset-admin-password", password="newpass", stdout=out)
    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.check_password("newpass")


@pytest.mark.django_db
def test_random_password():
    out = StringIO()
    call_command("reset-admin-password", random=True, stdout=out)
    user = User.objects.get(username="admin")
    assert user.is_superuser is True
    assert user.is_staff is True
    output = out.getvalue()
    assert "Successfully set" in output
    password = output.split('"')[-2]
    assert len(password) == 20
    assert user.check_password(password)
