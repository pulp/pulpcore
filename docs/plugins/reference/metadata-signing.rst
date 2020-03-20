.. _metadata-signing:

Metadata Signing
================

.. note::

    Content Signing is in tech-preview and may change in backwards incompatible ways in future
    releases.

Plugin writers wishing to enable users to sign metadata need to add a new field ``metadata_signing_service``
to their implementation of a repository and/or publication. This field should be exposed to users who consume
content via REST API. The users may afterwards specify which signing service will be used to sign the
metadata when creating a publication.

Every signing service will always be an instance of a subclass of the ``SigningService`` model. Plugin
writers may either use the existing ``AsciiArmoredDetachedSigningService``, or use that as a reference for
writing their own signing service model.

The ``SigningService`` base class already provides the fully implemented ``sign()`` method, the signature of
the ``validate()`` method (which must be implemented by each subclass), and the ``save()`` method (which
calls the ``validate()`` method, but is otherwise fully implemented).

In order to sign metadata, plugin writers are required to call the ``sign()`` method of the signing service
being used. This method invokes the signing script (or other executable) which is provided by the
administrator who instantiates a concrete signing service. Instantiating/creating a concrete signing service
will ultimately call the ``save()`` method, which will in turn call ``validate()``. As a result, it is up to
the ``validate()`` method to ensure the signing service script provided by the administrator actually provides
any signatures, signature files, and return values, as required by the individual ``SigningService`` subclass.

This is why implementing a signing service model other than ``AsciiArmoredDetachedSigningService`` simply
requires inheriting from ``SiginingService`` and then implementing ``validate()``.

.. note::
    The existing ``AsciiArmoredDetachedSigningService`` requires a signing script that creates a detached
    ascii-armored signature file, and prints valid JSON in the following format to stdout:

        {"file": "filename", "signature": "filename.asc", "key": "public.key"}

    Here "filename" is a path to the original file that was signed (passed to the signing script by the
    ``sign()`` method), "filename.asc" is a path to the signature file created by the script, and "public.key"
    is a path to the signature file containing the public key used by the script.

    This json is converted to a python dict and returned by the ``sign()`` method. If an error occurs, a
    runtime error is raised instead. All of this is enforced by the ``validate()`` method at the time of
    instantiation.

    For more information see the corresponding :ref:`workflow documentation <configuring-signing>`.

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
