from gettext import gettext as _
from types import SimpleNamespace


# Special purpose advisory locks for use with the two number variant.
# The group will be 0.
# The numbers are randomly chosen.
# !!! Never change these values !!!
TASK_DISPATCH_LOCK = 21
TASK_SCHEDULING_LOCK = 42
TASK_UNBLOCKING_LOCK = 84
TASK_METRICS_HEARTBEAT_LOCK = 74
STORAGE_METRICS_LOCK = 72


#: All valid task states.
TASK_STATES = SimpleNamespace(
    WAITING="waiting",
    SKIPPED="skipped",
    RUNNING="running",
    COMPLETED="completed",
    FAILED="failed",
    CANCELED="canceled",
    CANCELING="canceling",
)

# The same as above, but in a format that choice fields can use
TASK_CHOICES = (
    (TASK_STATES.WAITING, "Waiting"),
    (TASK_STATES.SKIPPED, "Skipped"),
    (TASK_STATES.RUNNING, "Running"),
    (TASK_STATES.COMPLETED, "Completed"),
    (TASK_STATES.FAILED, "Failed"),
    (TASK_STATES.CANCELED, "Canceled"),
    (TASK_STATES.CANCELING, "Canceling"),
)

#: Tasks in a final state have finished their work.
TASK_FINAL_STATES = (
    TASK_STATES.SKIPPED,
    TASK_STATES.COMPLETED,
    TASK_STATES.FAILED,
    TASK_STATES.CANCELED,
)

#: Tasks in an incomplete state have not finished their work yet.
TASK_INCOMPLETE_STATES = (TASK_STATES.WAITING, TASK_STATES.RUNNING, TASK_STATES.CANCELING)


SYNC_MODES = SimpleNamespace(ADDITIVE="additive", MIRROR="mirror")
SYNC_CHOICES = (
    (SYNC_MODES.ADDITIVE, "Add new content from the remote repository."),
    (
        SYNC_MODES.MIRROR,
        "Add new content and remove content is no longer in the remote repository.",
    ),
)

# What content-identifying checksums algorithms does pulp _know about_?
# NOTE that models.Artifact must include a field for each possible checksum; simply
# adding here won't make a new type-of checksum available. sha256 MUST be here,
# as Pulp relies on it to identify entities.
ALL_KNOWN_CONTENT_CHECKSUMS = {"md5", "sha1", "sha224", "sha256", "sha384", "sha512"}


FS_EXPORT_METHODS = SimpleNamespace(
    WRITE="write",
    HARDLINK="hardlink",
    SYMLINK="symlink",
)
FS_EXPORT_CHOICES = (
    (FS_EXPORT_METHODS.WRITE, "Export by writing"),
    (FS_EXPORT_METHODS.HARDLINK, "Export by hardlinking"),
    (FS_EXPORT_METHODS.SYMLINK, "Export by symlinking"),
)

EXPORT_BATCH_SIZE = 2000

# Mapping of http-response-headers to what various block-storage-apis call them
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_object.html
# response-headers S3 respects, and what they map to in an S3 object
S3_RESPONSE_HEADER_MAP = {
    "Content-Disposition": "ResponseContentDisposition",
    "Content-Type": "ResponseContentType",
    "Cache-Control": "ResponseCacheControl",
    "Content-Language": "ResponseContentLanguage",
    "Expires": "ResponseExpires",
    "Content-Encoding": "ResponseContentEncoding",
}
# https://learn.microsoft.com/en-us/python/api/azure-storage-blob/azure.storage.blob.contentsettings?view=azure-python
# response-headers azure respects, and what they map to in an azure object
AZURE_RESPONSE_HEADER_MAP = {
    "Content-Disposition": "content_disposition",
    "Content-Type": "content_type",
    "Cache-Control": "cache_control",
    "Content-Language": "content_language",
    "Content-Encoding": "content_encoding",
}
# https://gcloud.readthedocs.io/en/latest/storage-blobs.html
# response-headers Google Cloud Storage respects, and what they map to in a GCS object
GCS_RESPONSE_HEADER_MAP = {
    "Content-Disposition": "content_disposition",
    "Content-Type": "content_type",
    "Cache-Control": "cache_control",
    "Content-Language": "content_language",
    "Content-Encoding": "content_encoding",
}

# Storage-type mapped to storage-response-map
STORAGE_RESPONSE_MAP = {
    "storages.backends.s3boto3.S3Boto3Storage": S3_RESPONSE_HEADER_MAP,
    "storages.backends.azure_storage.AzureStorage": AZURE_RESPONSE_HEADER_MAP,
    "storages.backends.gcloud.GoogleCloudStorage": GCS_RESPONSE_HEADER_MAP,
}

# Message users receive when attempting to delete a protected repo version
PROTECTED_REPO_VERSION_MESSAGE = _(
    "The repository version cannot be deleted because it (or its publications) are currently being "
    "used to distribute content. Please update the necessary distributions first."
)
