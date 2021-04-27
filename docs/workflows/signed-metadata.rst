.. _configuring-signing:

Metadata Signing
----------------

.. note::

    Content Signing is in tech-preview and may change in backwards incompatible ways in future
    releases.

Administrators can add signing services to Pulp using the command line tools. Users
may then associate the signing services with repositories that support content signing.
The example below demonstrates how a signing service can be created using ``gpg``:

1. Make sure the service user ``pulp`` has access to ``gpg`` and that the keypair is
   installed in its keyrings. The private key might alternatively be provided by a
   hardware cryptographic device.

2. Create a signing script that accepts a file name as the only argument. The script
   needs to generate an ascii-armored detached GPG signature for that file. The script
   should then print out a JSON structure with the following format. All the file names
   are relative paths inside the current working directory::

       {"file": "filename", "signature": "filename.asc"}

   The filename must remain the same for the detached signature, as shown.

   .. note::

      Plugins may provide other signing service classes that may need their JSON output to
      contain different information.

   Below is an example of a signing script:

   .. code-block:: bash

       #!/usr/bin/env bash

       FILE_PATH=$1
       SIGNATURE_PATH="$1.asc"

       ADMIN_ID="658285BA1A648083"
       PASSWORD="password"

       # Create a detached signature
       gpg --quiet --batch --pinentry-mode loopback --yes --passphrase \
          $PASSWORD --homedir ~/.gnupg/ --detach-sign --default-key $ADMIN_ID \
          --armor --output $SIGNATURE_PATH $FILE_PATH

       # Check the exit status
       STATUS=$?
       if [ $STATUS -eq 0 ]; then
          echo {\"file\": \"$FILE_PATH\", \"signature\": \"$SIGNATURE_PATH\"}
       else
          exit $STATUS
       fi

   .. note::

       Make sure the script contains a proper shebang and Pulp has got valid permissions
       to execute it.

3. Create a signing service consisting of an absolute path to the script and a meaningful
   name describing the script's purpose. It is possible to insert the signing service in
   to a database by using the ``pulpcore-manager shell_plus`` interactive Python shell. Here is an
   example showing how to create one instance pointing to a script:

   .. code-block:: python

       from pulpcore.app.models.content import AsciiArmoredDetachedSigningService

       # read an already exported public key
       with open("public.key") as key:
           AsciiArmoredDetachedSigningService.objects.create(
               name="sign-metadata",
               public_key=key.read(),
               pubkey_fingerprint="19CD52BD1CA9A00DF10A842D74B14E3590C2231F",
               script="/var/lib/pulp/scripts/sign-metadata.sh",
           )

   .. note::

       While creating a signing service, the model ``AsciiArmoredDetachedSigningService``
       runs additional checks in order to prevent saving invalid scripts to the database.
       This feature enables administrators to validate their signing scripts in advance.

   .. note::

      You can use `pulpcore-manager add-signing-service` to add a ``SigningService``.
      This command is however still in tech-preview.

4. Retrieve and check the saved signing service via REST API::

       $ http :24817/pulp/api/v3/signing-services/

       {
           "count": 1,
           "next": null,
           "previous": null,
           "results": [
               {
                   "name": "sign-metadata",
                   "pubkey_fingerprint": "19CD52BD1CA9A00DF10A842D74B14E3590C2231F",
                   "public_key": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n [...] \n-----END PGP PUBLIC KEY BLOCK-----\n",
                   "pulp_created": "2020-11-06T15:42:20.645197Z",
                   "pulp_href": "/pulp/api/v3/signing-services/ffb9e987-952f-47e3-a274-ffe69a80ded7/",
                   "script": "/var/lib/pulp/sign-metadata.sh"
               }
           ]
       }

Plugin writers are then able to sign selected content by the provided script. To learn more
about the signing from a plugin's perspective, see the section :ref:`metadata-signing`.
