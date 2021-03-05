Due to the removal of ``md5`` and ``sha1`` from the ``ALLOWED_CONTENT_CHECKSUMS`` setting, every
system that had any Artifacts synced in in prior to 3.11 will have to run the ``pulpcore-manager
handle-content-checksums`` command. A data migration is provided with 3.11 that will run this
automatically as part of the ``pulpcore-manager migrate`` command all upgrades must run anyway.
