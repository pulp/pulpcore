Added a redirecting content guard that can be employed by plugins to generate preauthenticated URLs
that forward from a REST call to the content app. Added the ``GetOrCreateSerializerMixin`` to
``get_or_create`` objects still validating them through the serializer.
