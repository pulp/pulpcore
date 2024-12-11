# Configure Storage Backend

Pulp uses [django-storages](https://django-storages.readthedocs.io) to support multiple storage backends.
See the reference for the [`STORAGES` settings](site:pulpcore/docs/admin/reference/settings.md).

## Local Filesystem

This is the default storage backend Pulp will use if another is not specified.

### Configure

Configure the `BACKEND` and `OPTIONS` for the default django storage.

Example configuration:

```python
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "file_permissions_mode": 0o600,
            "directory_permissions_mode": 0o600,
        },
    },
}
```

Compreheensive options for Local Filesystem can be found in
[Django docs](https://docs.djangoproject.com/en/4.2/ref/files/storage/#django.core.files.storage.FileSystemStorage).

### Further notes

- Read about how Pulp's modifies `MEDIA_ROOT` defaults [here]().
- Other relevant settings (module-scope settings) that are left as Django default's:
    * `MEDIA_URL`
    * `FILE_UPLOAD_PERMISSIONS`
    * `FILE_UPLOAD_DIRECTORY_PERMISSIONS`

## Amazon S3

### Amazon Setup

Before you can configure Amazon S3 storage to use with Pulp, ensure that you complete the following steps.
To complete these steps, consult the official Amazon S3 documentation.

1. Set up an AWS account.
2. Create an S3 bucket for Pulp to use.
3. In AWS Identity and Access Management (IAM), create a user that Pulp can use to access your S3 bucket.
4. Save the access key id and secret access key.

### Pulp Setup

**TODO: learn how that works for oci-images and operator and provide links**

To have Pulp use S3, complete the following steps.
This assumes a simple install. For oci-images:
* ...
* ...

#### Install Python Dependencies

Ensure you have `django-storages` and `boto3` in your environement.

For example:

```bash
pip install django-storages[boto3]
```

#### Configure

Configure the `BACKEND` and `OPTIONS` for the default django storage.

Here is an example configuration that will use a bucket called `pulp3` that is hosted in
region `eu-central-1`:

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

Compreheensive options for Amazon S3 can be found in
[`django-storages` docs](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html#configuration-settings).

#### Further notes

- You can omit `access_key` and `secret_key` if the following are true:
    * The system that hosts Pulp is running in AWS
    * The [`instance_profile`](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2_instance-profiles.html) provides access to the S3 bucket

## Azure Blob storage

### Azure Setup

Before you can configure Azure Blob storage to use with Pulp, ensure that you complete the following steps.
To complete these steps, consult the official Azure Blob documentation.

1. Set up an Azure account and create a storage account.
2. In your storage account, create a container under `Blob` service.
3. Obtain the access credentials so that you can later configure Pulp to access your Azure Blob storage. You can find the access credentials
   at the storage account level, at Access keys (these are automatically generated).

### Pulp Setup

#### Install Python Dependencies

Ensure you have `django-storages[azure]` in your environement:

```bash
pip install django-storages[azure]
```

#### Configure

```python
MEDIA_ROOT = ""
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.azure_storage.AzureStorage",
        "OPTIONS": {
            "account_name": '<storage account name>',
            "azure_container": '<container name>',  # As created within the blob service of your storage account
            "account_key": '<Key1 or Key2>',  # From the access keys of your storage account
            "expiration_secs": 60,
            "overwrite_files": 'True',
            "location": '<path>'  # The folder within the container where your pulp objects will be stored
        },
    },
}
```

Compreheensive options for Azure Blob can be found in
[`django-storages` docs](https://django-storages.readthedocs.io/en/latest/backends/azure.html#configuration-settings).

