import pytest

from rest_framework import serializers

from pulpcore.app.serializers import OrphansCleanupSerializer


@pytest.mark.parametrize("value", [-1, 4294967296])
def test_orphan_protection_time(value):
    """
    Test that OrphansCleanupSerializer is not valid if the "orphan_protection_time"
    value is not in the range defined by ORPHAN_PROTECTION_TIME_LOWER_BOUND
    and ORPHAN_PROTECTION_TIME_UPPER_BOUND.
    """
    serializer = OrphansCleanupSerializer(data={"orphan_protection_time": value})

    with pytest.raises(serializers.ValidationError):
        serializer.is_valid(raise_exception=True)
