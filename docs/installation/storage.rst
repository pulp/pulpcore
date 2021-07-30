.. _storage:

Storage
=======

-----------

  Pulp uses `django-storages <https://django-storages.readthedocs.io/>`_ to support multiple storage
  backends. If no backend is configured, Pulp will by default use the local filesystem. If you want
  to use another storage backend such as Amazon Simple Storage Service (S3), you'll need to
  configure Pulp.

  You can also configure Pulp to use Amazon S3 and Azure storage using the Pulp installer. For more information
  see the `Pulp installer documentation <https://docs.pulpproject.org/pulp_installer/quickstart/#storage>`_

Amazon S3
^^^^^^^^^

Setting up S3
-------------

Before you can configure Amazon S3 storage to use with Pulp, ensure that you complete the following steps.
To complete these steps, consult the official Amazon S3 documentation.

1. Set up an AWS account.
2. Create an S3 bucket for Pulp to use.
3. In AWS Identity and Access Management (IAM), create a user that Pulp can use to access your S3 bucket.
4. Save the access key id and secret access key.

Configuring Pulp to use Amazon S3
---------------------------------

To have Pulp use S3, complete the following steps:

1. Install the optional django-storages and boto3 Python packages in the pulp virtual environment::

      pip install django-storages[boto3]

2. Depending on which method you use to install or configure Pulp, you must set ``DEFAULT_FILE_STORAGE`` to ``storages.backends.s3boto3.S3Boto3Storage`` in Pulp Settings. For example, if you use the `Pulp installer <https://docs.pulpproject.org/pulp_installer/quickstart/>`_, the ``default_file_storage`` is part of the ``pulp_settings`` Ansible variables you can define in your Ansible playbook.

3. In that same way, add your Amazon S3 configuration settings to ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``, and ``AWS_STORAGE_BUCKET_NAME``. For more S3 configuration options, see the `django-storages documents <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html>`_.

4. Set the ``MEDIA_ROOT`` configuration option. This will be the path in your bucket that Pulp will use. If you want Pulp to create its folders in the top level of the bucket, an empty string is acceptable.

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

Before you can configure Azure Blob storage to use with Pulp, ensure that you complete the following steps.
To complete these steps, consult the official Azure Blob documentation.

1. Set up an Azure account and create a storage account.
2. In your storage account, create a container under `Blob` service.
3. Obtain the access credentials so that you can later configure Pulp to access your Azure Blob storage. You can find the access credentials
   at the storage account level, at Access keys (these are automatically generated).

Configuring Pulp to use Azure Blob storage
------------------------------------------

1. Install the optional django-storages[azure] package in the pulp virtual environment::

      pip install django-storages[azure]

2. Depending on which method you use to install or configure Pulp, you must set ``DEFAULT_FILE_STORAGE`` to ``storages.backends.azure_storage.AzureStorage`` in Pulp Settings. For example, if you use the `Pulp installer <https://docs.pulpproject.org/pulp_installer/quickstart/>`_, the ``default_file_storage`` is part of the ``pulp_settings`` Ansible variables you can define in your Ansible playbook.
3. In the same way, configure the following parameters::

      AZURE_ACCOUNT_NAME = 'Storage account name'
      AZURE_CONTAINER = 'Container name (as created within the blob service of your storage account)'
      AZURE_ACCOUNT_KEY = 'Key1 or Key2 from the access keys of your storage account'
      AZURE_URL_EXPIRATION_SECS = 60
      AZURE_OVERWRITE_FILES = 'True'
      AZURE_LOCATION = 'the folder within the container where your pulp objects will be stored'

  For a comprehensive overview of all possible options for the Azure Blob storage backend see the `django-storages[azure] documents
  <https://django-storages.readthedocs.io/en/latest/backends/azure.html>`_.
