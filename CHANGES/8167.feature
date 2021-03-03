The fields ``proxy_username`` and ``proxy_password`` have been added to remotes.
Credentials can no longer be specified as part of the ``proxy_url``.
A data migration will move the proxy auth information on existing remotes to the new fields.
