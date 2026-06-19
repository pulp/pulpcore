import pytest
from rest_framework import serializers

from pulpcore.app.serializers.fields import relative_path_validator


@pytest.mark.parametrize(
    ("path",),
    [
        pytest.param("/absolute/path", id="absolute"),
        pytest.param("../sneaky/path", id="path_traversal"),
        pytest.param("suspicious/../../sneaky/path", id="hidden_path_traversal"),
    ],
)
def test_relative_path_validator_rejects(path):
    with pytest.raises(serializers.ValidationError):
        relative_path_validator(path)
