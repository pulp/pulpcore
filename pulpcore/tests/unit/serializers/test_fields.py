import pytest
from rest_framework import serializers

from pulpcore.app.serializers import fields
from pulpcore.app.serializers.fields import pulp_labels_validator


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
