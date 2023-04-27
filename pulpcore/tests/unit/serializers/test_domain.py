import pytest
from types import SimpleNamespace

from rest_framework import serializers

from pulpcore.app.serializers.domain import (
    FileSystemSettingsSerializer,
    # SFTPSettingsSerializer,
    AmazonS3SettingsSerializer,
    AzureSettingsSerializer,
    # GoogleSettingsSerializer,
    DomainSerializer,
)


MIN_DOMAIN_SETTINGS = {
    "name": "hello",
    "storage_settings": {},
    "redirect_to_object_storage": True,
}


@pytest.fixture(autouse=True)
def _no_validate_storage_backend(monkeypatch):
    # Ensure the validate method does not perform the backend installation check
    monkeypatch.setattr(DomainSerializer, "_validate_storage_backend", lambda *args: None)


@pytest.fixture(
    params=[
        "pulpcore.app.models.storage.FileSystem",
        "storages.backends.s3boto3.S3Boto3Storage",
        "storages.backends.azure_storage.AzureStorage",
    ]
)
def storage_class(request):
    return request.param


@pytest.fixture
def serializer_class(storage_class):
    if storage_class == "pulpcore.app.models.storage.FileSystem":
        return FileSystemSettingsSerializer
    elif storage_class == "storages.backends.s3boto3.S3Boto3Storage":
        return AmazonS3SettingsSerializer
    elif storage_class == "storages.backends.azure_storage.AzureStorage":
        return AzureSettingsSerializer


@pytest.fixture
def required_settings(storage_class):
    if storage_class == "pulpcore.app.models.storage.FileSystem":
        return {"location": "/var/lib/pulp/media/"}
    elif storage_class == "storages.backends.s3boto3.S3Boto3Storage":
        return {"access_key": "testing", "secret_key": "secret", "bucket_name": "test"}
    elif storage_class == "storages.backends.azure_storage.AzureStorage":
        return {"account_name": "test", "account_key": "secret", "azure_container": "test"}


@pytest.fixture
def all_settings(serializer_class, required_settings):
    serializer = serializer_class()
    fields = serializer.get_fields()
    default_settings = {
        name: field.default
        for name, field in fields.items()
        if not field.required and not field.read_only
    }
    return {**required_settings, **default_settings}


def test_minimal_storage_settings(storage_class, required_settings, all_settings):
    domain = SimpleNamespace(storage_class=storage_class, **MIN_DOMAIN_SETTINGS)
    data = {"storage_settings": {}}
    serializer = DomainSerializer(domain, data=data, partial=True)

    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert "This field is required" in str(exc_info.value)
    for field_name, value in required_settings.items():
        assert field_name in str(exc_info.value)

    data["storage_settings"].update(required_settings)
    serializer = DomainSerializer(domain, data=data, partial=True)
    serializer.is_valid(raise_exception=True)

    storage_settings = serializer.validated_data["storage_settings"]
    assert storage_settings == all_settings


def test_unknown_settings(storage_class, required_settings):
    domain = SimpleNamespace(storage_class=storage_class, **MIN_DOMAIN_SETTINGS)
    data = {"storage_settings": {"foo": "bar", **required_settings}}
    serializer = DomainSerializer(domain, data=data, partial=True)

    with pytest.raises(serializers.ValidationError) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert "foo" in str(exc_info.value)
    assert "Unexpected field" in str(exc_info.value)


def test_using_setting_names(storage_class, serializer_class, all_settings):
    settings_name_map = serializer_class.SETTING_MAPPING
    settings = {k.upper(): all_settings[v] for k, v in settings_name_map.items()}

    domain = SimpleNamespace(storage_class=storage_class, **MIN_DOMAIN_SETTINGS)
    data = {"storage_settings": settings}
    serializer = DomainSerializer(domain, data=data, partial=True)

    serializer.is_valid(raise_exception=True)

    storage_settings = serializer.validated_data["storage_settings"]
    assert storage_settings == all_settings


class DomainSettingsBaseMixin:
    storage_class = None
    serializer_class = None
    required_settings = {}

    @classmethod
    def setUpClass(cls):
        serializer = cls.serializer_class()
        fields = serializer.get_fields()
        cls.default_settings = {
            name: field.default
            for name, field in fields.items()
            if not field.required and not field.read_only
        }
        cls.all_settings = {**cls.required_settings, **cls.default_settings}


def test_hidden_settings(storage_class, serializer_class, all_settings):
    fields = serializer_class().get_fields()
    hidden_field_names = [name for name, field in fields.items() if field.write_only]
    domain = SimpleNamespace(
        name="hello",
        storage_class=storage_class,
        storage_settings=all_settings,
    )
    serializer = DomainSerializer(domain)
    serializer.fields.pop("pulp_href")
    assert "hidden_fields" in serializer.data["storage_settings"]
    hidden_fields = serializer.data["storage_settings"]["hidden_fields"]

    assert len(hidden_fields) == len(hidden_field_names)
    hidden_fields = {item["name"]: item["is_set"] for item in hidden_fields}
    for field in hidden_field_names:
        assert field in hidden_fields
        is_set = bool(all_settings[field])
        assert hidden_fields[field] == is_set


# class TestDomainSFTPSettingsSerializer(DomainSettingsBaseMixin, TestCase):
#     storage_class = "pulpcore.app.models.storage.PulpSFTPStorage"
#     serializer_class = SFTPSettingsSerializer
#     required_settings = {"host": "http://testing", "root_path": "/storage_sftp/"}
#
#     @classmethod
#     def setUpClass(cls):
#         super().setUpClass()
#         cls.min_domain_settings["redirect_to_object_storage"] = False


# class TestDomainGoogleSettingsSerializer(DomainSettingsBaseMixin, TestCase):
#     storage_class = "storages.backends.gcloud.GoogleCloudStorage"
#     serializer_class = GoogleSettingsSerializer
#     required_settings = {"bucket_name": "test", "project_id": "testtest"}
