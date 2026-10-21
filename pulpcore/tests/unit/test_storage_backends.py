"""Tests for the stable Domain storage boundary."""

from io import BytesIO

import pytest
from django.test import override_settings

from pulpcore.app.checks import storage_redirect_backend
from pulpcore.app.models.domain import Domain, storages
from pulpcore.app.serializers.domain import (
    BACKEND_CHOICES,
    BackendChoiceField,
    DomainBackendMigratorSerializer,
)
from pulpcore.app.storage_backends import (
    backend_id,
    backend_path,
    legacy_backend_path,
    open_stream,
    signed_url,
)


def test_backend_choice_preserves_legacy_api_values():
    """Older processes and clients continue to receive class-path identifiers."""
    field = BackendChoiceField(choices=BACKEND_CHOICES)
    assert (
        field.to_internal_value("storages.backends.s3boto3.S3Boto3Storage")
        == "storages.backends.s3boto3.S3Boto3Storage"
    )
    assert field.to_representation("s3") == "storages.backends.s3.S3Storage"
    assert field.to_internal_value("filesystem") == "pulpcore.app.models.storage.FileSystem"
    assert "storages.backends.s3boto3.S3Boto3Storage" in dict(BACKEND_CHOICES)


def test_backend_migration_preserves_legacy_path():
    """The background migration task stores a path older Pulp can interpret."""
    serializer = DomainBackendMigratorSerializer(
        data={
            "storage_class": "pulpcore.app.models.storage.FileSystem",
            "storage_settings": {"location": "/tmp/media"},
        }
    )
    serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["storage_class"] == "pulpcore.app.models.storage.FileSystem"


class FirstStorage:
    """A test implementation of Pulp's versioned Domain settings factory."""

    @classmethod
    def from_domain_settings(cls, settings, schema_version):
        """Record the settings contract received by the selected implementation."""
        instance = cls()
        instance.settings = settings
        instance.schema_version = schema_version
        return instance


class SecondStorage(FirstStorage):
    """A replacement implementation using the same persisted Domain record."""


class CustomRedirectStorage:
    """An unregistered default backend with Pulp's redirect hook."""

    def pulp_url(self, name, headers=None, method=None):
        """Return a URL using Pulp's provider-neutral arguments."""
        return f"https://example.test/{name}"


@pytest.mark.parametrize(
    ("path", "expected_ids"),
    [
        ("pulpcore.app.models.storage.FileSystem", []),
        ("storages.backends.s3.S3Storage", []),
        ("pulpcore.tests.unit.test_storage_backends.CustomRedirectStorage", []),
        ("pulpcore.tests.unit.test_storage_backends.FirstStorage", ["pulpcore.E003"]),
        ("missing.storage.Backend", ["pulpcore.E003"]),
    ],
)
def test_storage_redirect_backend_check(path, expected_ids):
    """Only default classes with a supported content-serving path pass the check."""
    with override_settings(
        STORAGES={"default": {"BACKEND": path}}, REDIRECT_TO_OBJECT_STORAGE=True
    ):
        assert [error.id for error in storage_redirect_backend(None)] == expected_ids


@override_settings(
    STORAGES={"default": {"BACKEND": "pulpcore.tests.unit.test_storage_backends.FirstStorage"}},
    REDIRECT_TO_OBJECT_STORAGE=False,
)
def test_storage_redirect_backend_check_is_skipped_without_redirects():
    """A default backend needs no redirect hook when Pulp streams content itself."""
    assert storage_redirect_backend(None) == []


def test_domain_implementation_can_change_without_updating_record():
    """The process cache follows the implementation setting, not only row timestamps."""
    domain = Domain(
        name="other",
        storage_class="pulpcore.app.models.storage.FileSystem",
        storage_settings={"location": "/tmp/media"},
    )
    first_path = "pulpcore.tests.unit.test_storage_backends.FirstStorage"
    second_path = "pulpcore.tests.unit.test_storage_backends.SecondStorage"
    try:
        with override_settings(DOMAIN_STORAGE_BACKENDS={"filesystem": first_path}):
            first = domain.get_storage()
            assert isinstance(first, FirstStorage)
            assert first.schema_version == 1
            assert first.settings["location"] == "/tmp/media"
        with override_settings(DOMAIN_STORAGE_BACKENDS={"filesystem": second_path}):
            second = domain.get_storage()
            assert isinstance(second, SecondStorage)
            assert domain.storage_class == "pulpcore.app.models.storage.FileSystem"
    finally:
        storages.pop(domain.pulp_id, None)


@override_settings(DOMAIN_STORAGE_BACKENDS={"s3": "example.adapters.S3Storage"})
def test_implementation_mapping_does_not_change_backend_id():
    """A deployment can replace code without updating a Domain row."""
    assert backend_id("example.adapters.S3Storage") == "s3"
    assert backend_path("s3") == "example.adapters.S3Storage"
    assert legacy_backend_path("example.adapters.S3Storage") == "storages.backends.s3.S3Storage"


def test_s3_signed_url_translates_headers_and_method():
    """The django-storages adapter receives only provider-supported URL options."""

    class Storage:
        def url(self, name, **kwargs):
            assert name == "artifact/abc"
            assert kwargs == {
                "parameters": {
                    "ResponseContentDisposition": "attachment;filename=abc",
                    "ResponseContentType": "text/plain",
                },
                "http_method": "HEAD",
            }
            return "https://example.test/signed"

    assert (
        signed_url(
            Storage(),
            "s3",
            "artifact/abc",
            headers={
                "Content-Disposition": "attachment;filename=abc",
                "Content-Type": "text/plain",
                "Ignored": "value",
            },
            method="HEAD",
        )
        == "https://example.test/signed"
    )


def test_native_stream_is_bounded_and_closed_on_early_exit():
    """The Pulp boundary delegates ranges to implementations that support them."""
    calls = []

    class Storage:
        def open_stream(self, name, start=0, length=None):
            from contextlib import contextmanager

            @contextmanager
            def stream():
                calls.append((name, start, length))
                try:
                    yield BytesIO(b"bc")
                finally:
                    calls.append("closed")

            return stream()

    with open_stream(Storage(), "artifact/abc", start=1, length=2) as stream:
        assert stream.read(1) == b"b"
    assert calls == [("artifact/abc", 1, 2), "closed"]


def test_fallback_stream_bounds_reads_and_closes_on_error():
    """The Django fallback cannot return bytes beyond the selected range."""
    file = BytesIO(b"abcdef")

    class Storage:
        def open(self, name, mode):
            assert (name, mode) == ("artifact/abc", "rb")
            return file

    with pytest.raises(RuntimeError), open_stream(Storage(), "artifact/abc", 1, 2) as stream:
        assert stream.read(10) == b"bc"
        assert stream.read(10) == b""
        raise RuntimeError("stop")
    assert file.closed
