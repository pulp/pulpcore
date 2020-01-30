.. _metadata-signing:

Metadata Signing
================

.. note::

    Content Signing is in tech-preview and may change in backwards incompatible ways in future
    releases.

Plugin writers wishing to enable users to sign metadata need to add a new field ``metadata_signing_service``
to their implementation of a repository. This field should be exposed to users who consume content
via REST API. The users may afterwards specify which kind of a signing service will be used to sign the
metadata when creating a publication.

In order to sign metadata, plugin writers are required to call the method ``sign()`` of the subclasses
inheriting from the model ``SigningService``. This method invokes a signing script which is provided by
an administrator and creates a detached ascii-armored signature if called via the class
``AsciiArmoredDetachedSigningService``.

The following procedure may be taken into account for the plugin writers:

    1. Let us assume that a file repository contains the field ``metadata_signing_service``:

       .. code-block:: python

           metadata_signing_service = models.ForeignKey(
               AsciiArmoredDetachedSigningService,
               on_delete=models.SET_NULL,
               null=True
           )

       In the serializer, there is also added a corresponding field that serializes ``metadata_signing_service``,
       like so:

       .. code-block:: python

           metadata_signing_service = serializers.HyperlinkedRelatedField(
               help_text="A reference to an associated signing service.",
               view_name="signing-services-detail",
               queryset=models.AsciiArmoredDetachedSigningService.objects.all(),
               many=False,
               required=False,
               allow_null=True
           )

    2. Retrieve a desired signing script via the field ``metadata_signing_service`` stored in the repository:

       .. code-block:: python

           metadata_signing_service = FileRepository.objects.get(name='foo').metadata_signing_service

       A plugin writer can create a new repository with an associated signing service in the following two ways:

           - Using Python:

             .. code-block:: python

                 signing_service = AsciiArmoredDetachedSigningService.objects.get(name='sign-metadata')
                 FileRepository.objects.create(name='foo', metadata_signing_service=signing_service)

           - Using HTTP calls:

             .. code-block:: bash

                 http POST :24817/pulp/api/v3/repositories/file/file/ name=foo metadata_signing_service=http://localhost:24817/pulp/api/v3/signing-services/5506c8ac-8eae-4f34-bb5a-3bc08f82b088/

    3. Sign a file by calling the method ``sign()`` inside the context manager implemented in pulpcore, i.e.
       :class:`pulpcore.plugin.tasking.WorkingDirectory`:

       .. code-block:: python

           with WorkingDirectory():
               try:
                   signature = metadata_signing_service.sign(metadata.filepath)
               except RuntimeError:
                   raise
               add_to_repository(metadata, signature)

.. note::

    Plugin authors should be aware of the output format returned by a signing service and consider
    further actions according to that. Currently, only one output format is supported::

        {"file": "filename", "signature": "filename.asc", "key": "public.key"}

    The method ``sign()`` of the model ``AsciiArmoredDetachedSigningService`` returns a dictionary object
    in this format when no errors occur during the signing. Otherwise, a runtime error is raised.
