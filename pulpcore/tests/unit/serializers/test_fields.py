import pytest
from rest_framework import serializers

from pulpcore.app.serializers import fields
from pulpcore.app.serializers.fields import (
    PgpKeyFingerprintField,
    pulp_labels_validator,
)


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param({"key": "value"}, id="normal"),
        pytest.param({"key": ""}, id="empty-value"),
        pytest.param({"key": None}, id="none-value"),
        pytest.param({"key1": "value", "key2": None, "key3": ""}, id="multiple-keys"),
        pytest.param({"my-key": "value"}, id="dash-key"),
        pytest.param({"my.key": "value"}, id="dotted-key"),
        pytest.param({"my key": "value"}, id="spaced-key"),
        pytest.param({"my-dotted.key": "value"}, id="dotted-dash-key"),
        pytest.param({"spaced key-with.mixed_chars": "value"}, id="all-key"),
    ],
)
def test_pulp_labels_validator_valid(labels):
    """Valid label keys and values should pass validation."""
    result = pulp_labels_validator(labels)
    assert result == labels


@pytest.mark.parametrize(
    "labels",
    [
        pytest.param({"key": "val,ue"}, id="comma-value"),
        pytest.param({"key": "val(ue"}, id="open-parenthesis-value"),
        pytest.param({"key": "val)ue"}, id="close-parenthesis-value"),
        pytest.param({"bad!key": "value"}, id="exclamation-key"),
        pytest.param({"bad:key": "value"}, id="colon-key"),
        pytest.param({"bad@key": "value"}, id="at-sign-key"),
    ],
)
def test_pulp_labels_validator_invalid(labels):
    """Invalid label keys or values should raise ValidationError."""
    with pytest.raises(serializers.ValidationError):
        pulp_labels_validator(labels)


@pytest.mark.parametrize(
    "field_and_data",
    [
        (fields.JSONDictField, '{"foo": 123, "bar": [1,2,3]}'),
        (fields.JSONListField, '[{"foo": 123}, {"bar": 456}]'),
    ],
)
@pytest.mark.parametrize("binary_arg", [True, False])
def test_custom_json_dict_field(field_and_data, binary_arg):
    """
    On the happy overlap case,
    pulpcore JSONDictField and JSONListField should be compatible with drf JSONField.
    """
    custom_field, data = field_and_data
    drf_json_field = serializers.JSONField(binary=binary_arg)
    custom_field = custom_field(binary=binary_arg)
    custom_field_result = custom_field.to_internal_value(data)
    drf_field_result = drf_json_field.to_internal_value(data)
    assert custom_field_result == drf_field_result


@pytest.mark.parametrize(
    "field_and_data",
    [
        (fields.JSONDictField, '[{"foo": 123}, {"bar": 456}]'),
        (fields.JSONDictField, "123"),
        (fields.JSONDictField, "false"),
        (fields.JSONListField, '{"foo": 123, "bar": [1,2,3]}'),
        (fields.JSONListField, "123"),
        (fields.JSONListField, "false"),
    ],
)
@pytest.mark.parametrize("binary_arg", [True, False])
def test_custom_json_dict_field_raises(field_and_data, binary_arg):
    """
    On the invalid data case,
    pulpcore JSONDictField and JSONListField should raise appropriately.
    """
    custom_field, data = field_and_data
    custom_field = custom_field(binary=binary_arg)
    error_msg = "Invalid type"
    with pytest.raises(serializers.ValidationError, match=error_msg):
        custom_field.to_internal_value(data)


# -- PgpKeyFingerprintField tests --


@pytest.mark.parametrize(
    "value, expected",
    [
        pytest.param(
            "v4:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "v4:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v4-uppercase",
        ),
        pytest.param(
            "v4:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "v4:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v4-lowercase-normalized",
        ),
        pytest.param(
            "v6:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "v6:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v6-64hex",
        ),
        pytest.param(
            "keyid:AAAAAAAAAAAAAAAA",
            "keyid:AAAAAAAAAAAAAAAA",
            id="keyid-16hex",
        ),
        pytest.param(
            "keyid:aaaaaaaaaaaaaaaa",
            "keyid:AAAAAAAAAAAAAAAA",
            id="keyid-lowercase-normalized",
        ),
        pytest.param(
            "v3:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "v3:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v3-32hex",
        ),
    ],
)
def test_pgp_key_fingerprint_field_valid(value, expected):
    """Valid fingerprint formats should be accepted and normalized."""
    field = PgpKeyFingerprintField()
    assert field.to_internal_value(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("not-a-fingerprint", id="garbage"),
        pytest.param("v4:ZZZZ", id="non-hex-chars"),
        pytest.param("v4:AAAA", id="too-short-hex"),
        pytest.param("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", id="no-prefix"),
        pytest.param("v4:", id="empty-hex"),
        pytest.param("", id="empty-string"),
        pytest.param("keyid:AAAAAAAAAAAAAAA", id="keyid-15hex-too-short"),
        pytest.param("keyid:AAAAAAAAAAAAAAAAA", id="keyid-17hex-too-long"),
        pytest.param(
            "KEYID:AAAAAAAAAAAAAAAA",
            id="keyid-uppercase-prefix",
        ),
        pytest.param(
            "V4:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v4-uppercase-prefix",
        ),
        pytest.param(
            "V3:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v3-uppercase-prefix",
        ),
        pytest.param(
            "V6:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            id="v6-uppercase-prefix",
        ),
        pytest.param(
            "KeyId:AAAAAAAAAAAAAAAA",
            id="keyid-mixed-case-prefix",
        ),
    ],
)
def test_pgp_key_fingerprint_field_invalid(value):
    """Invalid fingerprint formats should raise ValidationError."""
    field = PgpKeyFingerprintField()
    with pytest.raises(serializers.ValidationError):
        field.to_internal_value(value)


def test_pgp_key_fingerprint_field_default_max_length():
    """Field should have a default max_length of 68."""
    field = PgpKeyFingerprintField()
    assert field.max_length == 68


def test_pgp_key_fingerprint_field_custom_max_length():
    """Custom max_length should override the default."""
    field = PgpKeyFingerprintField(max_length=100)
    assert field.max_length == 100


@pytest.mark.parametrize(
    "value, expected",
    [
        ("v4:aabbccdd", "v4:AABBCCDD"),
        ("keyid:aabbccdd", "keyid:AABBCCDD"),
        ("nocolon", "nocolon"),
    ],
)
def test_pgp_key_fingerprint_field_normalize(value, expected):
    """PgpKeyFingerprintField.normalize should uppercase hex after the colon."""
    assert PgpKeyFingerprintField.normalize(value) == expected
