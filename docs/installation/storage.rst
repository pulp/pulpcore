Storage
=======

.. _storage:

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

  To have Pulp use S3, you'll need to install the optional django-storages Python package::

      pip install django-storages

  Next you'll need to set ``DEFAULT_FILE_STORAGE`` to ``storages.backends.s3boto3.S3Boto3Storage``
  in your Pulp settings. At a minimum, you'll also need to set ``AWS_ACCESS_KEY_ID``,
  ``AWS_SECRET_ACCESS_KEY``, and ``AWS_STORAGE_BUCKET_NAME``. For more S3 configuration options, see
  the `django-storages documents <https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html>`_.

  You will also want to set the ``MEDIA_ROOT`` configuration option. This will be the path in your
  bucket that Pulp will use. An empty string is acceptable as well if you want Pulp to create its
  folders in the top level of the bucket.

  Here is an example configuration that will use a bucket called ``pulp3``::

        AWS_ACCESS_KEY_ID = 'AKIAIT2Z5TDYPX3ARJBA'
        AWS_SECRET_ACCESS_KEY = 'qR+vjWPU50fCqQuUWbj9Fain/j2pV+ZtBCiDiieS'
        AWS_STORAGE_BUCKET_NAME = 'pulp3'
        DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
        MEDIA_ROOT = ''
