Administration
==============

Administrators are responsible for deploying and configuring Pulp.

Content Signing
---------------

Administrators can add signing services to Pulp using the command line tools. Users
may then associate the signing services with repositories that support content signing.
The example below demonstrates how a signing service can be created using ``gpg``:

1. Create a signing script that accepts a file name as the only argument. The script
   needs to generate an ascii-armored detached GPG signature for that file. The script
   should then print out a JSON structure with the following format. All the file names
   are relative paths inside the current working directory::

       {"file": "filename", "signature": "filename.asc", "key": "public.key"}

   This is an example of a signing script:

   .. code-block:: bash

       #!/usr/bin/env bash

       FILE_PATH=$1
       SIGNATURE_PATH="$1.asc"
       PUBLIC_KEY_PATH="public.key"

       ADMIN_ID="27B3E8915B0C58FB"
       PASSWORD="password"

       # Export a public key
       gpg --armor --export admin@example.com > $PUBLIC_KEY_PATH

       # Create a detached signature
       gpg --quiet --batch --pinentry-mode loopback --yes --passphrase \
           $PASSWORD --homedir ~/.gnupg/ --detach-sign --default-key $ADMIN_ID \
           --armor --output $SIGNATURE_PATH $FILE_PATH

       # Check the exit status
       STATUS=$?
       if [ $STATUS -eq 0 ]; then
           echo {\"file\": \"$FILE_PATH\", \"signature\": \"$SIGNATURE_PATH\", \
               \"key\": \"$PUBLIC_KEY_PATH\"}
       else
           exit $STATUS
       fi

2. Create a signing service consisting of an absolute path to the script and a meaningful
   name describing the script's purpose. It is possible to insert the signing service in
   to a database by leveraging the utility ``django-admin shell_plus``:

   .. code-block:: python

       from pulpcore.app.models.content import SigningService

       SigningService.objects.create(
           name="sign-metadata",
           script="/var/lib/pulp/scripts/sign-metadata.sh"
       )

3. Retrieve and check the saved signing service via REST API::

       $ http :24817/pulp/api/v3/signing-services/

       {
           "count": 1,
           "next": null,
           "previous": null,
           "results": [
               {
                   "name": "sign-metadata",
                   "pulp_created": "2020-01-20T15:20:40.098923Z",
                   "pulp_href": "/pulp/api/v3/signing-services/601feba7-a5d9-4f0a-919b-77be52fad0f7/",
                   "script": "/var/lib/pulp/scripts/sign-metadata.sh"
               }
           ]
       }
