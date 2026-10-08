"""Temporary private streaming adapters for object-storage response bodies.

django-storages file objects are seekable Django file objects. Opening one for
reading downloads the complete object into a temporary file, which is unsuitable
for the content app's bounded response loop. These adapters expose only the
synchronous `open/read/close` interface needed by :mod:`pulpcore.responses`.

Remove these adapters when django-storages provides a stable, cross-backend,
streaming-read API that Pulp can use instead.
"""

from typing import Any

S3_STORAGE_CLASSES = frozenset(
    (
        "storages.backends.s3.S3Storage",
        "storages.backends.s3boto3.S3Boto3Storage",
    )
)
AZURE_STORAGE_CLASSES = frozenset(("storages.backends.azure_storage.AzureStorage",))
STREAMING_STORAGE_CLASSES = S3_STORAGE_CLASSES | AZURE_STORAGE_CLASSES

# These are the read arguments accepted by boto3's get_object operation and by
# s3transfer's download argument filter.  The import is optional because pulpcore
# can be installed without the S3 extra.
try:
    from s3transfer.constants import ALLOWED_DOWNLOAD_ARGS as _S3_DOWNLOAD_ARGS
except ImportError:  # pragma: no cover - exercised only without the S3 extra
    _S3_DOWNLOAD_ARGS = (
        "ChecksumMode",
        "ExpectedBucketOwner",
        "IfMatch",
        "IfModifiedSince",
        "IfNoneMatch",
        "IfUnmodifiedSince",
        "PartNumber",
        "RequestPayer",
        "SSECustomerAlgorithm",
        "SSECustomerKey",
        "SSECustomerKeyMD5",
        "VersionId",
    )


def _filter_s3_download_params(params: dict[str, Any]) -> dict[str, Any]:
    """Retain only configured values accepted by boto3 `get_object`."""

    return {key: value for key, value in params.items() if key in _S3_DOWNLOAD_ARGS}


def _clean_s3_name(name):
    """Match django-storages' logical-name processing before adding `location`."""

    try:
        from storages.utils import clean_name
    except ImportError:  # pragma: no cover - S3 storage requires django-storages
        import posixpath

        cleaned_name = posixpath.normpath(name).replace("\\", "/")
        if name.endswith("/") and not cleaned_name.endswith("/"):
            cleaned_name += "/"
        return "" if cleaned_name == "." else cleaned_name
    return clean_name(name)


class S3Stream:
    """A ranged reader backed by the configured django-storages S3 client."""

    def __init__(self, storage, name: str, offset: int, count: int):
        self.storage = storage
        self.name = name
        self.offset = offset
        self.count = count
        self.body = None

    def open(self):
        name = _clean_s3_name(self.name)
        key = self.storage._normalize_name(name)
        # `get_object_parameters` receives the logical name; `Key` includes
        # the backend's location prefix just as django-storages' `open` does.
        params = _filter_s3_download_params(self.storage.get_object_parameters(name))
        params.update(
            Bucket=self.storage.bucket_name,
            Key=key,
            Range=f"bytes={self.offset}-{self.offset + self.count - 1}",
        )
        response = self.storage.connection.meta.client.get_object(**params)
        self.body = response["Body"]
        return self

    def read(self, size: int) -> bytes:
        return self.body.read(size)

    def close(self):
        if self.body is not None:
            self.body.close()
            self.body = None


class AzureStream:
    """A ranged reader backed by an Azure `StorageStreamDownloader`."""

    def __init__(self, storage, name: str, offset: int, count: int):
        self.storage = storage
        self.name = name
        self.offset = offset
        self.count = count
        self.downloader = None
        self.chunks = None
        self.pending = b""
        self.remaining = count

    def open(self):
        path = self.storage._get_valid_path(self.name)
        self.downloader = self.storage.client.download_blob(
            path,
            offset=self.offset,
            length=self.count,
            timeout=self.storage.timeout,
        )
        self.chunks = iter(self.downloader.chunks())
        self.pending = b""
        self.remaining = self.count
        return self

    def read(self, size: int) -> bytes:
        # Azure controls chunk sizes. Retain at most one partially consumed chunk.
        if self.remaining == 0:
            return b""
        if size is None or size < 0 or size > self.remaining:
            size = self.remaining
        while len(self.pending) < size:
            try:
                self.pending += next(self.chunks)
            except StopIteration:
                break

        chunk = self.pending[:size]
        self.pending = self.pending[size:]
        self.remaining -= len(chunk)
        return chunk

    def close(self):
        """Release adapter references; Azure exposes no public downloader closer."""

        self.downloader = None
        self.chunks = None
        self.pending = b""
        self.remaining = 0


def get_stream(storage_class: str, storage, name: str, offset: int, count: int):
    """Return an adapter for a supported storage class, or `None` for fallback."""

    if storage_class in S3_STORAGE_CLASSES:
        return S3Stream(storage, name, offset, count)
    if storage_class in AZURE_STORAGE_CLASSES:
        return AzureStream(storage, name, offset, count)
    return None
