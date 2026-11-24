"""Backwards compat shim."""

from pulpcore.vendor.storages.backends.s3 import S3File as S3Boto3StorageFile  # noqa
from pulpcore.vendor.storages.backends.s3 import S3ManifestStaticStorage  # noqa
from pulpcore.vendor.storages.backends.s3 import S3StaticStorage  # noqa
from pulpcore.vendor.storages.backends.s3 import S3Storage as S3Boto3Storage  # noqa
