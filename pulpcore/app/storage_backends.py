"""Pulp's stable identifiers and operations for domain storage backends.

The identifiers in this module describe the storage service, not the Python class
used to access it. Changing an implementation must not change a Domain record.
"""

from contextlib import contextmanager
from types import SimpleNamespace

from django.conf import settings
from django.utils.module_loading import import_string

from pulpcore.constants import STORAGE_BACKENDS, STORAGE_RESPONSE_MAP

LEGACY_STORAGE_CLASSES = SimpleNamespace(
    FILESYSTEM="pulpcore.app.models.storage.FileSystem",
    S3BOTO3="storages.backends.s3boto3.S3Boto3Storage",
    S3="storages.backends.s3.S3Storage",
    AZURE="storages.backends.azure_storage.AzureStorage",
    GCS="storages.backends.gcloud.GoogleCloudStorage",
)

LEGACY_BACKENDS = {
    LEGACY_STORAGE_CLASSES.FILESYSTEM: STORAGE_BACKENDS.FILESYSTEM,
    LEGACY_STORAGE_CLASSES.S3BOTO3: STORAGE_BACKENDS.S3,
    LEGACY_STORAGE_CLASSES.S3: STORAGE_BACKENDS.S3,
    LEGACY_STORAGE_CLASSES.AZURE: STORAGE_BACKENDS.AZURE,
    LEGACY_STORAGE_CLASSES.GCS: STORAGE_BACKENDS.GCS,
}

LEGACY_BACKEND_PATHS = {
    STORAGE_BACKENDS.FILESYSTEM: LEGACY_STORAGE_CLASSES.FILESYSTEM,
    STORAGE_BACKENDS.S3: LEGACY_STORAGE_CLASSES.S3,
    STORAGE_BACKENDS.AZURE: LEGACY_STORAGE_CLASSES.AZURE,
    STORAGE_BACKENDS.GCS: LEGACY_STORAGE_CLASSES.GCS,
}

BACKEND_IDS = frozenset(vars(STORAGE_BACKENDS).values())
URL_RESPONSE_HEADERS = frozenset().union(*(mapping for mapping in STORAGE_RESPONSE_MAP.values()))


def backend_id(value):
    """Return a stable ID for a built-in or configured implementation path.

    Unknown paths return `None`; they are not treated as importable Domain
    backends merely because they happen to be present on `sys.path`.
    """
    if not isinstance(value, str):
        return None
    if value in BACKEND_IDS:
        return value
    if value in LEGACY_BACKENDS:
        return LEGACY_BACKENDS[value]
    for kind, path in settings.DOMAIN_STORAGE_BACKENDS.items():
        if value == path and kind in BACKEND_IDS:
            return kind
    return None


def default_backend_id():
    """Identify the default Django storage without relying on its class path.

    Unrecognized custom default storages retain their path for compatibility,
    but cannot use Pulp's provider-specific redirect behavior.
    """
    path = settings.STORAGES["default"]["BACKEND"]
    return backend_id(path) or path


def legacy_backend_path(value):
    """Return a class-path identifier understood by older Pulp processes.

    Existing legacy paths, including the deprecated S3 alias, are preserved.
    Stable IDs and configured implementation paths use a canonical legacy path.
    """
    if not isinstance(value, str):
        return value
    if value in LEGACY_BACKENDS:
        return value
    kind = backend_id(value)
    return LEGACY_BACKEND_PATHS.get(kind, value)


def backend_path(kind):
    """Return the deployment-selected class path for a stable backend ID."""
    kind = backend_id(kind)
    if kind is None:
        raise ValueError("Unknown storage backend")
    return settings.DOMAIN_STORAGE_BACKENDS[kind]


def backend_class(kind):
    """Import the deployment-selected Django storage implementation."""
    return import_string(backend_path(kind))


def signed_url(storage, kind, name, headers=None, method=None):
    """Create a URL using Pulp's provider-neutral response-header interface.

    A replacement storage can implement `pulp_url` to translate headers and
    HTTP methods itself. The fallback preserves django-storages URL semantics.
    """
    response_headers = {
        header: value
        for header, value in (headers or {}).items()
        if header in URL_RESPONSE_HEADERS and value is not None
    }
    if callable(pulp_url := getattr(storage, "pulp_url", None)):
        return pulp_url(name, headers=response_headers, method=method)

    kind = backend_id(kind)
    if kind not in STORAGE_RESPONSE_MAP:
        raise NotImplementedError(f"Storage backend {kind!r} does not support redirects.")
    parameters = {
        provider_header: value
        for header, provider_header in STORAGE_RESPONSE_MAP[kind].items()
        if (value := response_headers.get(header)) is not None
    }
    if kind == STORAGE_BACKENDS.S3:
        return storage.url(name, parameters=parameters, http_method=method)
    return storage.url(name, parameters=parameters)


class _BoundedReader:
    """Limit each read and total bytes returned by a Django file object."""

    def __init__(self, file, length):
        self.file = file
        self.remaining = length

    def read(self, size=-1):
        """Read at most `size` bytes, never beyond the selected range."""
        if self.remaining is not None:
            size = self.remaining if size is None or size < 0 else min(size, self.remaining)
        data = self.file.read(size)
        if self.remaining is not None:
            self.remaining -= len(data)
        return data


@contextmanager
def open_stream(storage, name, start=0, length=None):
    """Open a bounded read stream and close it on exit, including after errors.

    Backends with native ranged reads should implement `open_stream`. The
    Django `open` fallback bounds bytes returned but may still buffer the
    entire object internally, depending on the installed implementation.
    """
    if start < 0 or (length is not None and length < 0):
        raise ValueError("Stream start and length must be non-negative")
    if callable(native := getattr(storage, "open_stream", None)):
        with native(name, start=start, length=length) as stream:
            yield _BoundedReader(stream, length)
    else:
        with storage.open(name, "rb") as file:
            file.seek(start)
            yield _BoundedReader(file, length)
