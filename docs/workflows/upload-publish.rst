Upload and Publish
==================

Uploading Content
-----------------

Content can be uploaded by POSTing the the file to ``/pulp/api/v3/content/<plugin_name>/<content_type>/``.
Some plugins can create the content unit completely from that file, but others require some
additional attributes to be specified with the upload. See your plugin documentation for more info
on upload features of your plugin.

File data can be uploaded in parallel, and then the call to
``/pulp/api/v3/content/<plugin_name>/<content_type>/`` can reference the already existing Artifact to create
the content from.


Associating with a Repository on Upload
---------------------------------------

You can automatically associate newly uploaded content with a Repository when using the
``/pulp/api/v3/content/<plugin_name>/<content_type>/`` API by passing the ``repository reference``.


Chunked Uploads
---------------

For large file uploads, Pulp provides an `Uploads API <../../restapi.html#tag/uploads>`_. To begin
uploading a file in chunks, an initial POST request must be sent to the ``/pulp/api/v3/uploads``
endpoint with the total size of the file::

    http POST :24817/pulp/api/v3/uploads/ size=10485760

This returns an upload href (e.g. ``/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/``) that can
be used for chunks. Chunks can be uploaded in any order or in parallel::

    http --form PUT :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/ file@./chunk2 'Content-Range:bytes 6291456-10485759/*'
    http --form PUT :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/ file@./chunk1 'Content-Range:bytes 0-6291455/*'

Note: You can send an optional sha256 argument::

    http --form PUT :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/ file@./chunk1 'Content-Range:bytes 0-6291455/*' sha256=7ffc86295de63e96006ce5ab379050628aa5d51f816267946c71906594e13870

Once all chunks have been uploaded, a final POST request with the file sha256 can be sent to
complete the upload::

    http POST :24817/pulp/api/v3/uploads/a8b5a7f7-2f22-460d-ab20-d5616cb71cdd/commit sha256=abc123...

This queues a task that creates an artifact, and the upload gets deleted and cannot be re-used.

Putting this altogether, here is an example that uploads a 1.iso file in two chunks::

   curl -O https://fixtures.pulpproject.org/file-large/1.iso
   split --bytes=6M 1.iso chunk
   export UPLOAD=$(http POST :24817/pulp/api/v3/uploads/ size=`ls -l 1.iso | cut -d ' ' -f5` | jq -r '.pulp_href')
   http --form PUT :24817$UPLOAD file@./chunkab 'Content-Range:bytes 6291456-10485759/*'
   http --form PUT :24817$UPLOAD file@./chunkaa 'Content-Range:bytes 0-6291455/*'
   http POST :24817${UPLOAD}commit/ sha256=`sha256sum 1.iso | cut -d ' ' -f1`

.. note::

    Each uploaded chunk is stored as a separate file in the default storage. When an upload is
    committed, uploaded chunks are removed automatically and a new artifact is created, as usually.
