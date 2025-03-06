import pytest
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.exceptions import ValidationError

from pulpcore.app.util import get_url, get_prn
from pulpcore.app.serializers import UserRoleSerializer, GroupRoleSerializer
from pulp_file.app.models import FileRepository


pytestmark = [pytest.mark.django_db]


@pytest.fixture(params=[UserRoleSerializer, GroupRoleSerializer])
def serializer_class(request):
    return request.param


@pytest.fixture
def context(db, serializer_class):
    request = Mock()
    if serializer_class == UserRoleSerializer:
        User = get_user_model()
        user = User.objects.create()
        request.resolver_match.kwargs = {"user_pk": user.pk}
    elif serializer_class == GroupRoleSerializer:
        group = Group.objects.create()
        request.resolver_match.kwargs = {"group_pk": group.pk}
    else:
        pytest.fail("This fixture received an unknown serializer class.")
    return {"request": request}


@pytest.fixture
def repository(db):
    return FileRepository.objects.create(name="test1")


@pytest.mark.parametrize(
    "field",
    [
        "role",
        "content_object",
        "content_object_prn",
    ],
)
def test_nested_role_serializer_has_certain_fields(serializer_class, field):
    serializer = serializer_class()
    assert field in serializer.fields


def test_nested_role_serializer_fails_without_content(serializer_class, context):
    data = {"role": "file.filerepository_owner"}
    serializer = serializer_class(data=data, context=context)
    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)


def test_nested_role_serializer_with_null_content(serializer_class, context):
    data = {"role": "file.filerepository_owner", "content_object": None}
    serializer = serializer_class(data=data, context=context)
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["content_object"] is None


def test_nested_role_serializer_with_null_content_prn(serializer_class, context):
    data = {"role": "file.filerepository_owner", "content_object_prn": None}
    serializer = serializer_class(data=data, context=context)
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["content_object"] is None


def test_nested_role_serializer_allows_href(serializer_class, context, repository):
    data = {"role": "file.filerepository_owner", "content_object": get_url(repository)}
    serializer = serializer_class(data=data, context=context)
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["content_object"] == repository


def test_nested_role_serializer_allows_prn(serializer_class, context, repository):
    data = {"role": "file.filerepository_owner", "content_object_prn": get_prn(repository)}
    serializer = serializer_class(data=data, context=context)
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["content_object"] == repository
