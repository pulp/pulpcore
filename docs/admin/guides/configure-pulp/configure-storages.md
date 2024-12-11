# Configure Storage Backend

Pulp uses [django-storages](https://django-storages.readthedocs.io) to support multiple storage backends.
See the reference for the [`STORAGES` settings](site:pulpcore/docs/admin/reference/settings/#storages).

## Modifying the settings

The settings can be updated via the `settings.py` file or through environment variables
and have support to dynaconf merge features (learn more on the [Settings Introduction](site:pulpcore/docs/admin/guides/configure-pulp/introduction/)).

To learn where and how to modify the files and environment variables, refer to the appropriate installation method documentation:

* [Container (single-process) quickstart](site:pulp-oci-images/docs/admin/tutorials/quickstart/#single-container)
* [Container (multi-process) quickstart](site:pulp-oci-images/docs/admin/tutorials/quickstart/#podman-or-docker-compose)
* [Pulp Operator quickstart](site:pulp-operator/docs/admin/tutorials/quickstart-kubernetes/)

## Local Filesystem (default)

### Example

In this example, the storage file permission and `MEDIA_ROOT` are overridden:

```python
STORAGES = {
    "default": {
        "BACKEND": "pulpcore.app.models.storage.FileSystem",
        "OPTIONS": {
            "file_permissions_mode": 0o600,
            "directory_permissions_mode": 0o600,
        },
    },
}
MEDIA_ROOT="/custom/media/root"  # default: /var/lib/pulp/media
```

Notes:

* The [`MEDIA_ROOT`](site:pulpcore/docs/admin/reference/settings/#media_root) setting specifies where Pulp
will save the files.
* Pulp customizes Django's default class, `django.core.files.storage.FileSystemStorage`. The original can't be used.
* There are some other related global definitions provided by django:
    * `MEDIA_URL`
    * `FILE_UPLOAD_PERMISSIONS`
    * `FILE_UPLOAD_DIRECTORY_PERMISSIONS`

Comprehensive options for Local Filesystem can be found in
[Django docs](https://docs.djangoproject.com/en/4.2/ref/files/storage/#django.core.files.storage.FileSystemStorage).

## Amazon S3

### Setup

Before you can configure Amazon S3 storage to use with Pulp, ensure that you complete the following steps
(consult the official Amazon S3 docs for precise steps).

1. Set up an AWS account.
2. Create an S3 bucket for Pulp to use.
3. In AWS Identity and Access Management (IAM), create a user that Pulp can use to access your S3 bucket.
4. Save the access key id and secret access key.

### Example

In this example, the storage uses a bucket called `pulp3` that is hosted in region `eu-central-1`:

```python
MEDIA_ROOT = ""
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": 'AKIAIT2Z5TDYPX3ARJBA',
            "secret_key": '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',
            "bucket_name": 'pulp3',
            "signature_version": "s3v4",
            "addressing_style": "path",
            "region_name": "eu-central-1",
        },
    },
}
```

Notes:

* `MEDIA_ROOT` must be set to an empty string.
* You can omit `access_key` and `secret_key` if:
    1. The system that hosts Pulp is running on AWS
    2. And the [`instance_profile`](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2_instance-profiles.html) provides access to the S3 bucket

Comprehensive options for Amazon S3 can be found in
[`django-storages` docs](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#configuration-settings).

## S3 Compatible

The same `storages.backends.s3.S3Storage` backend can be used for S3 Compatible API services, such as [Minio](https://min.io/), [Ceph/RADOS](https://docs.ceph.com/en/reef/man/8/rados/) and [Backblaze B2](https://www.backblaze.com/cloud-storage).

The [django-storages](https://django-storages.readthedocs.io/en/latest/backends/s3_compatible/index.html) documentation
provides a reference for setting up some of these services.

## Azure Blob storage

### Setup

Before you can configure Azure Blob storage to use with Pulp, ensure that you complete the following steps
(consult the official Azure documentation for precise steps).

1. Set up an Azure account and create a storage account.
2. In your storage account, create a container under `Blob` service.
3. Obtain the access credentials so that you can later configure Pulp to access your Azure Blob storage. You can find the access credentials
   at the storage account level, at Access keys (these are automatically generated).

### Example

In this example, the storage uses a container called `pulp3` with the `pulp-account` username.

```python
MEDIA_ROOT = ""
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.azure_storage.AzureStorage",
        "OPTIONS": {
            "account_name": 'pulp-account',
            "azure_container": 'pulp3',
            "account_key": 'Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==',
            "expiration_secs": 60,
            "overwrite_files": 'True',
            "location": 'pulp3'
        },
    },
}
```

Notes:

* `MEDIA_ROOT` must be set to an empty string.

Comprehensive options for Azure Blob can be found in
[`django-storages` docs](https://django-storages.readthedocs.io/en/latest/backends/azure.html#configuration-settings).
