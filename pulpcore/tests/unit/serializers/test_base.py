import pytest

from rest_framework import serializers

from pulpcore.app.serializers import (
    validate_unknown_fields,
    RBACContentGuardSerializer,
    GetOrCreateSerializerMixin,
)
from pulpcore.app.models import RBACContentGuard
from pulpcore.app.util import get_domain


def test_unknown_field():
    """
    Test disjoint sets of `initial_data` with a single field and `defined_fields`.
    """
    initial_data = {"unknown1": "unknown"}
    defined_fields = {"field1": 1, "field2": 2}

    pytest.raises(
        serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
    )


def test_unknown_fields():
    """
    Test disjoint sets of `initial_data` with multiple fields and `defined_fields`.
    """
    initial_data = {"unknown1": "unknown", "unknown2": "unknown", "unknown3": "unknown"}
    defined_fields = {"field1": 1, "field2": 2}

    pytest.raises(
        serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
    )


def test_mixed_initial_data():
    """
    Test where `defined_fields` is a proper subset of the `initial_data`.
    """
    initial_data = {
        "field1": 1,
        "field2": 2,
        "unknown1": "unknown",
        "unknown2": "unknown",
        "unknown3": "unknown",
    }
    defined_fields = {"field1": 1, "field2": 2}
    pytest.raises(
        serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
    )


def test_mixed_incomplete_initial_data():
    """
    Test where `initial_data` and `defined_fields` are intersecting sets.
    """
    initial_data = {
        "field2": 2,
        "unknown1": "unknown",
        "unknown2": "unknown",
        "unknown3": "unknown",
    }
    defined_fields = {"field1": 1, "field2": 2}
    pytest.raises(
        serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
    )


def test_empty_defined_fields():
    """
    Test an empty `defined_fields`.
    """
    initial_data = {
        "field2": 2,
        "unknown1": "unknown",
        "unknown2": "unknown",
        "unknown3": "unknown",
    }
    defined_fields = {}
    pytest.raises(
        serializers.ValidationError, validate_unknown_fields, initial_data, defined_fields
    )


def test_validate_no_unknown_fields():
    """
    Test where the `initial_data` is equal to `defined_fields`.
    """
    initial_data = {"field1": 1, "field2": 2}
    defined_fields = {"field1": 1, "field2": 2}
    validate_unknown_fields(initial_data, defined_fields)


def test_validate_no_unknown_fields_no_side_effects():
    """
    Test validation success where the `initial_data` is equal to `defined_fields`
    and that `initial_data` and `defined_fields` are not mutated.
    """
    initial_data = {"field1": 1, "field2": 2}
    defined_fields = {"field1": 1, "field2": 2}
    validate_unknown_fields(initial_data, defined_fields)

    assert initial_data == {"field1": 1, "field2": 2}
    assert defined_fields == {"field1": 1, "field2": 2}


def test_ignored_fields_no_side_effects():
    """
    Test ignored fields in initial data don't cause side effects
    """
    # there's just the `csrfmiddlewaretoken` in the ignored_fields
    initial_data = {"field1": 1, "csrfmiddlewaretoken": 2}
    defined_fields = {"field1": 1}
    validate_unknown_fields(initial_data, defined_fields)


@pytest.fixture
def guard_fixture(db):
    return RBACContentGuard.objects.get_or_create(name="test")[0]


class GuardSerializer(GetOrCreateSerializerMixin, RBACContentGuardSerializer):
    pass


def test_mixin_get(guard_fixture):
    """Test GetOrCreateSerializerMixin's get functionality."""
    natural_key = {"name": "test", "pulp_domain": get_domain()}
    guard = GuardSerializer.get_or_create(natural_key)
    assert guard.pk == guard_fixture.pk


def test_mixin_create(guard_fixture):
    """Test GetOrCreateSerializerMixin's create functionality.'"""
    natural_key = {"name": "test2", "pulp_domain": get_domain()}
    default_data = {"description": "hello"}
    guard = GuardSerializer.get_or_create(natural_key, default_data)
    assert guard.pk != guard_fixture.pk
    assert guard.description == default_data["description"]
