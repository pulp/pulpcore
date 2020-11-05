.. _storage:

Storage
=======

-----------

  Pulp uses `django-storages <https://django-storages.readthedocs.io/>`_ to support multiple storage
  backends. If no backend is configured, Pulp will by default use the local filesystem. If you want
  to use another storage backend such as Amazon Simple Storage Service (S3), you'll need to
  configure Pulp.

Amazon S3
^^^^^^^^^

Setting up S3
-------------

  In order to use Amazon S3, you'll need to set up an AWS account. Then you'll need to create a
  bucket for Pulp to use. Then you'll need to go into Identity and Access Management (IAM) in AWS to
  create a user that Pulp will use to access your S3 bucket. Save the access key id and secret
  access key.

Configuring Pulp
----------------

  To have Pulp use S3, you'll need to install the optional django-storages and boto3 Python packages in the pulp
  virtual environment::

      pip install django-storages[boto3]

  Next you'll need to set ``DEFAULT_FILE_STORAGE`` to ``storages.backends.s3boto3.S3Boto3Storage``
  in your Pulp settings. At a minimum, you'll also need to set ``AWS_ACCESS_KEY_ID``,
  ``AWS_SECRET_ACCESS_KEY``, and ``AWS_STORAGE_BUCKET_NAME``. For more S3 configuration options, see
  the `django-storages documents <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html>`_.

  You will also want to set the ``MEDIA_ROOT`` configuration option. This will be the path in your
  bucket that Pulp will use. An empty string is acceptable as well if you want Pulp to create its
  folders in the top level of the bucket.

  Here is an example configuration that will use a bucket called ``pulp3`` that is hosted in
  region ``eu-central-1``::

        AWS_ACCESS_KEY_ID = 'AKIAIT2Z5TDYPX3ARJBA'
        AWS_SECRET_ACCESS_KEY = 'qR+vjWPU50fCqQuUWbj9Fain/j2pV+ZtBCiDiieS'
        AWS_STORAGE_BUCKET_NAME = 'pulp3'
        AWS_DEFAULT_ACL = "@none None"
        S3_USE_SIGV4 = True
        AWS_S3_SIGNATURE_VERSION = "s3v4"
        AWS_S3_ADDRESSING_STYLE = "path"
        AWS_S3_REGION_NAME = "eu-central-1"
        DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
        MEDIA_ROOT = ''

  If the system that hosts Pulp is running in AWS and has been configured with an
  `instance profile <https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2_instance-profiles.html>`_
  that provides access to the S3 bucket you can omit the ``AWS_ACCESS_KEY_ID`` and
  ``AWS_SECRET_ACCESS_KEY`` parameters as the underlying ``boto3`` library will pick them up
  automatically.

  It is only necessary to set ``AWS_DEFAULT_ACL`` to ``"@none None"`` if you have set the
  ``BlockPublicAcls`` option in the Block Public Access settings of your bucket
  or of your AWS account. The default setting in the latest version of django-storages
  is `public-read`, which will get blocked. This is set to change in a
  `future release <https://django-storages.readthedocs.io/en/1.7.2/backends/amazon-S3.html>`_.

Azure Blob storage
^^^^^^^^^^^^^^^^^^

Setting up Azure Blob storage
-----------------------------

  In order to use Azure Blob Storage, you'll need to set up an Azure account. Then create a storage
  account, and in that storage account, create a container under Blob service. The access credentials
  can be found at the storage account level, at Access keys (these are automatically generated).

Configuring Pulp
----------------

  To have Pulp use Azure Blob storage, you'll need to install the optional django-storages[azure]
  package in the pulp virtual environment::

      pip install django-storages[azure]

  Next you'll need to set the ``DEFAULT_FILE_STORAGE`` to
  ``storages.backends.azure_storage.AzureStorage`` in your pulp settings, and configure following
  parameters in your pulp settings file (for a comprehensive overview of all possible options for
  the Azure Blob storage backend see the `django-storages[azure] documents
  <https://django-storages.readthedocs.io/en/latest/backends/azure.html>_`)::

      AZURE_ACCOUNT_NAME = 'Storage account name'
      AZURE_CONTAINER = 'Container name (as created within the blob service of your storage account)'
      AZURE_ACCOUNT_KEY = 'Key1 or Key2 from the access keys of your storage account'
      AZURE_URL_EXPIRATION_SECS = 60
      AZURE_OVERWRITE_FILES = 'True'
      AZURE_LOCATION = 'the folder within the container where your pulp objects will be stored'
