import pytest
from pulpcore.app.serializers import PulpExportSerializer


pytestmark = pytest.mark.usefixtures("fake_domain")


def test_validate_no_params():
    data = {}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()


def test_validate_bad_param_values():
    data = {"full": "bar", "dry_run": 0}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()


def test_bad_params():
    data = {"baz": "bar"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()


def test_read_only_params():
    data = {"full": True, "dry_run": False, "output_file_info": {"bar": "blech"}}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()

    with pytest.raises(AttributeError):
        serializer.output_file_info["bar"]


def test_chunk_size():
    # positive tests
    # bytes
    data = {"chunk_size": "100B"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == 100

    # kilobytes
    data = {"chunk_size": "100KB"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == 100 * 1024

    # megabytes
    data = {"chunk_size": "100MB"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == 100 * 1024 * 1024

    # gigabytes
    data = {"chunk_size": "100GB"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == 100 * 1024 * 1024 * 1024

    # terabytes
    data = {"chunk_size": "1TB"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == 1 * 1024 * 1024 * 1024 * 1024

    # float-units
    data = {"chunk_size": "2.4GB"}
    serializer = PulpExportSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["chunk_size"] == int(2.4 * 1024 * 1024 * 1024)

    # negative tests
    # no units
    data = {"chunk_size": "100"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()

    # not-a-number
    data = {"chunk_size": "bazMB"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()

    # non-positive
    data = {"chunk_size": "0GB"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()

    # non-positive
    data = {"chunk_size": "-10KB"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()

    # too many terabytes
    data = {"chunk_size": "100TB"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()

    # morbidly many megabytes
    data = {"chunk_size": "10000000000000M"}
    serializer = PulpExportSerializer(data=data)
    assert not serializer.is_valid()
