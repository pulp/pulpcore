from unittest import TestCase
from unittest.mock import patch
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


# Ensure the validate method does not perform the backend installation check
@patch.object(DomainSerializer, "_validate_storage_backend", lambda *args: None)
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
        cls.hidden_fields = [name for name, field in fields.items() if field.write_only]
        cls.all_settings = {**cls.required_settings, **cls.default_settings}
        cls.min_domain_settings = {
            "name": "hello",
            "storage_settings": {},
            "redirect_to_object_storage": True,
        }
        cls.maxDiff = None

    def test_minimal_storage_settings(self):
        domain = SimpleNamespace(storage_class=self.storage_class, **self.min_domain_settings)
        data = {"storage_settings": {}}
        serializer = DomainSerializer(domain, data=data, partial=True)

        with self.assertRaises(serializers.ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("This field is required", str(ctx.exception))
        for field_name, value in self.required_settings.items():
            self.assertIn(field_name, str(ctx.exception))

        data["storage_settings"].update(self.required_settings)
        serializer = DomainSerializer(domain, data=data, partial=True)
        serializer.is_valid(raise_exception=True)

        storage_settings = serializer.validated_data["storage_settings"]
        self.assertDictEqual(storage_settings, self.all_settings)

    def test_unknown_settings(self):
        domain = SimpleNamespace(storage_class=self.storage_class, **self.min_domain_settings)
        data = {"storage_settings": {"foo": "bar", **self.required_settings}}
        serializer = DomainSerializer(domain, data=data, partial=True)

        with self.assertRaises(serializers.ValidationError) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("foo", str(ctx.exception))
        self.assertIn("Unexpected field", str(ctx.exception))

    def test_using_setting_names(self):
        settings_name_map = self.serializer_class.SETTING_MAPPING
        settings = {k.upper(): self.all_settings[v] for k, v in settings_name_map.items()}

        domain = SimpleNamespace(storage_class=self.storage_class, **self.min_domain_settings)
        data = {"storage_settings": settings}
        serializer = DomainSerializer(domain, data=data, partial=True)

        serializer.is_valid(raise_exception=True)

        storage_settings = serializer.validated_data["storage_settings"]
        self.assertDictEqual(storage_settings, self.all_settings)

    def test_hidden_settings(self):
        domain = SimpleNamespace(
            name="hello",
            storage_class=self.storage_class,
            storage_settings=self.all_settings,
        )
        serializer = DomainSerializer(domain)
        serializer.fields.pop("pulp_href")
        self.assertIn("hidden_fields", serializer.data["storage_settings"])
        hidden_fields = serializer.data["storage_settings"]["hidden_fields"]

        self.assertEqual(len(self.hidden_fields), len(hidden_fields))
        hidden_fields = {item["name"]: item["is_set"] for item in hidden_fields}
        for field in self.hidden_fields:
            self.assertIn(field, hidden_fields)
            is_set = bool(self.all_settings[field])
            self.assertEqual(is_set, hidden_fields[field])


class TestDomainFileSettingsSerializer(DomainSettingsBaseMixin, TestCase):
    storage_class = "pulpcore.app.models.storage.FileSystem"
    serializer_class = FileSystemSettingsSerializer
    required_settings = {"location": "/var/lib/pulp/media/"}


# class TestDomainSFTPSettingsSerializer(DomainSettingsBaseMixin, TestCase):
#     storage_class = "pulpcore.app.models.storage.PulpSFTPStorage"
#     serializer_class = SFTPSettingsSerializer
#     required_settings = {"host": "http://testing", "root_path": "/storage_sftp/"}
#
#     @classmethod
#     def setUpClass(cls):
#         super().setUpClass()
#         cls.min_domain_settings["redirect_to_object_storage"] = False


class TestDomainS3SettingsSerializer(DomainSettingsBaseMixin, TestCase):
    storage_class = "storages.backends.s3boto3.S3Boto3Storage"
    serializer_class = AmazonS3SettingsSerializer
    required_settings = {"access_key": "testing", "secret_key": "secret", "bucket_name": "test"}


class TestDomainAzureSettingsSerializer(DomainSettingsBaseMixin, TestCase):
    storage_class = "storages.backends.azure_storage.AzureStorage"
    serializer_class = AzureSettingsSerializer
    required_settings = {"account_name": "test", "account_key": "secret", "azure_container": "test"}


# class TestDomainGoogleSettingsSerializer(DomainSettingsBaseMixin, TestCase):
#     storage_class = "storages.backends.gcloud.GoogleCloudStorage"
#     serializer_class = GoogleSettingsSerializer
#     required_settings = {"bucket_name": "test", "project_id": "testtest"}
