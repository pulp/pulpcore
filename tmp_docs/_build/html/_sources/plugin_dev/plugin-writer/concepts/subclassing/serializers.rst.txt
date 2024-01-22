.. _subclassing-serializers:

Serializers
===========

`Django Rest Framework Serializers <https://www.django-rest-framework.org/api-guide/serializers/>`_
work "both ways", translating user input to Python objects, and translating Python objects to
user-facing responses. Generally, plugins will create a serializer field for each field on their
model that should be user-facing.

Most plugins will implement:
 * serializer(s) for plugin specific content type(s), should be subclassed from one of
   NoArtifactContentSerializer, SingleArtifactContentSerializer, or
   MultipleArtifactContentSerializer, depending on the properties of the content type(s)
 * serializer(s) for plugin specific remote(s), should be subclassed from RemoteSerializer
 * serializer(s) for plugin specific publisher(s), should be subclassed from PublisherSerializer

Adding Fields
-------------

For each field on the corresponding model that should be readable or writable by the user, the
serializer needs to add that field as well.


.. code-block:: python

      class FileContentSerializer(SingleArtifactContentSerializer):
          """
          Serializer for File Content.
          """

          relative_path = serializers.CharField(
              help_text="Relative location of the file within the repository"
          )

      class Meta:
            fields = SingleArtifactContentSerializer.Meta.fields + ('relative_path',)
            model = FileContent

Help Text
^^^^^^^^^

The REST APIs of Pulp Core and each plugin are automatically documented using swagger. Each field's
documentation is generated using the ``help_text`` set on the serializer field, so please be sure
to set this for every field.


