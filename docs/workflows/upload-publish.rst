Upload and Publish
==================

Chunked Uploads
---------------

For large file uploads, Pulp provides an `Uploads API <../../restapi.html#tag/uploads>`_. To begin
uploading a file in chunks, an initial PUT request must be sent to the ``/pulp/api/v3/uploads``
endpoint::

    http --form PUT :24817/pulp/api/v3/uploads/ file@./chunkaa 'Content-Range:bytes 0-6291455/32095676'

This returns an upload href (e.g. ``/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/``) that can
be used for subsequent chunks::

    http --form PUT :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/ file@./chunkbb 'Content-Range:bytes 6291456-10485759/32095676'

Once all chunks have been uploaded, a final POST request with the file sha256 can be sent to complete the
upload::

    http --form POST :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/ sha256=d7c0953bd2a0c44b75844677ea839b2f3d40b5d3689c3b3756f3c2bc784eef3d

Then the artifact may be created with the upload href::

    http --form POST :24817/pulp/api/v3/artifacts/ upload=/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/

Note that after creating an artifact from an upload, the upload gets deleted and cannot be re-used.

Putting this altogether, here is an example that uploads a 1.iso file in two chunks::

   curl -O https://repos.fedorapeople.org/repos/pulp/pulp/fixtures/file-large/1.iso
   split --bytes=6M 1.iso chunk
   export UPLOAD=$(http --form PUT :24817/pulp/api/v3/uploads/ file@./chunkaa 'Content-Range:bytes 0-6291455/32095676'  | jq -r '._href')
   http --form PUT :24817$UPLOAD file@./chunkab 'Content-Range:bytes 6291456-10485759/32095676'
   http --form POST :24817$UPLOAD sha256=d7c0953bd2a0c44b75844677ea839b2f3d40b5d3689c3b3756f3c2bc784eef3d
   http POST :24817/pulp/api/v3/artifacts/ upload=$UPLOAD
