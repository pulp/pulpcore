# Replacing a Domain storage implementation

Domain records retain historical storage class paths so older Pulp processes can read them during
a rolling upgrade. Pulp resolves those paths to stable backend IDs (`filesystem`, `s3`, `azure`, and
`gcs`), then selects the installed class through `DOMAIN_STORAGE_BACKENDS`. The API still advertises
the historical class paths and returns them on reads. It also accepts stable IDs in raw requests,
but generated clients may reject those IDs because the schema still lists the historical paths.
Existing `S3Boto3Storage` paths are preserved rather than rewritten to the newer S3 path.

This boundary replaces the code for an existing storage type; it does not register a new type.
Only filesystem, S3, and Azure are currently offered for new Domains. GCS is recognized for
existing configurations, and SFTP is not supported.

## Select an implementation

Set the class path for each non-default Domain storage type you are replacing:

```python
DOMAIN_STORAGE_BACKENDS = {
    "filesystem": "pulpcore.app.models.storage.FileSystem",
    "s3": "my_storage.backends.s3.S3Storage",
    "azure": "storages.backends.azure_storage.AzureStorage",
    "gcs": "storages.backends.gcloud.GoogleCloudStorage",
}
```

The default Domain instead uses Django's `STORAGES["default"]`. When replacing that class, set
both its `BACKEND` and the corresponding `DOMAIN_STORAGE_BACKENDS` entry. The mapping lets Pulp
identify its storage type without requiring the replacement's Python path in a Domain record.
An unrecognized default class can serve redirects only if it implements `pulp_url`.

The existing settings serializer for each type validates `storage_settings` before Pulp constructs
the selected class. A replacement can accept the version-1 settings as keyword arguments or
provide `from_domain_settings(settings, schema_version=1)` to translate them. The factory receives
the validated settings dictionary; for S3, that includes a dictionary for `transfer_config`, not a
boto3 object. Reject settings the implementation cannot honor rather than silently ignoring them.
Changing `DOMAIN_STORAGE_BACKENDS` alone does not change the settings schema accepted by the API.

For direct content redirects, a replacement may implement
`pulp_url(name, headers=None, method=None)` to sign URLs with Pulp's response-header overrides.
Without that hook, Pulp calls the django-storages-style `url()` method for recognized object storage
types. For ranged content reads, a replacement may expose a synchronous
`open_stream(name, start=0, length=None)` context manager. Pulp falls back to Django's `open()` and
`seek()` if the hook is absent; that fallback bounds the returned bytes but may buffer a whole
remote object. The stream must release its resources when the context exits.

## Use storage from a plugin

Plugin code should use `pulpcore.plugin.util.get_local_storage_path(file, domain=None)` when it
needs an actual filesystem path. It returns `None` when the backend does not provide one; other
storage errors are propagated. Use `get_direct_storage_url(file, headers=None, http_method=None,
domain=None)` when a consumer needs a URL directly to object storage. It returns `None` when the
Domain uses filesystem storage or has redirects disabled, and raises `NotImplementedError` when
redirects are requested from an unsupported backend. Both functions accept a Pulp-managed file
such as `Artifact.file` or `PulpTemporaryFile.file`. If the file belongs to another Domain, pass
that Domain explicitly; otherwise they use the current Domain.

The URL function accepts generic `Content-Type` and `Content-Disposition` response headers and
translates them into the selected provider's signed URL parameters. Plugins should not inspect
`storage_class` or pass provider-specific parameters to `storage.url()`. The existing
`get_artifact_url(artifact, ...)` differs: it always returns a URL, falling back to the content
app when a direct URL is unavailable.

## Roll out a replacement

Keep the Domain's storage type, bucket or container, prefix, object names, credentials, and URL
behavior compatible. Install the replacement and its dependencies on every API, content, and worker
process, and test reads, writes, range requests, and signed redirects against existing objects.
Then change the deployment settings. A code-only change needs no Domain data migration. Moving
objects to a different location still requires a storage migration.

During a rolling upgrade, new processes continue to store and return historical class paths so
older processes can read the same Domain rows. Keep the old implementation installed until those
processes and the rollback window are gone. Do not switch persisted `storage_class` values to IDs
while any process still requires the historical paths.
