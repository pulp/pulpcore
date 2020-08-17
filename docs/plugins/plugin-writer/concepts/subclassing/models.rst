.. _subclassing-models:

Models
======

For the most part, models provided by plugin writers are just regular `Django Models
<https://docs.djangoproject.com/en/2.1/topics/db/models/>`_.

.. note::
   One slight variation is that the validation is primarily handled in the Django Rest Framework
   Serializer. ``.clean()`` is not called.

Most plugins will implement:
 * model(s) for the specific content type(s) used in the plugin, should be subclassed from Content model
 * model(s) for the plugin specific remote(s), should be subclassed from Remote model


Adding Model Fields
~~~~~~~~~~~~~~~~~~~

Each subclassed Model will typically store attributes that are specific to the content type. These
attributes need to be added to the model as ``fields``. You can use any of Django's field types
for your fields. See the `Django field documentation
<https://docs.djangoproject.com/en/2.1/ref/models/fields/>`_, for more in-depth information on
using these fields.

.. note::
   One of Pulp's goals is to work correctly on multiple databases. It is probably best to avoid
   fields that are not database agnostic. See Database Gotchas below.

.. note::
   It is required to declare the ``default_related_name``.

The TYPE class attribute is used for filtering purposes.

.. code-block:: python

        class FileContent(Content):
            """
            The "file" content type.

            Fields:
                digest (str): The SHA256 HEX digest.
            """
            TYPE = 'file'
            digest = models.TextField(null=False)

            class Meta:
                default_related_name = "%(app_label)s_%(model_name)s"


Here we create a new field using use Django's ``TextField``. After adding/modifying a model, you
can make and run database migrations with:


.. code-block:: bash

      pulpcore-manager makemigrations $PLUGIN_APP_LABEL
      pulpcore-manager migrate

If you recognize this syntax, it is because pulpcore-manager is ``manage.py`` configured with
``DJANGO_SETTINGS_MODULE="pulpcore.app.settings"``. You can use it anywhere you normally would use
``manage.py`` or ``django-admin``.


Uniqueness
~~~~~~~~~~

Model uniqueness (which will also be used as the natural key) is defined by an inner ``class
Meta``. Pulp Core enforces uniqueness constraints at the database level.

Adding to the simplified ``FileContent`` above:

.. code-block:: python

        class FileContent(Content):
            """
            The "file" content type.
            Content of this type represents a single file uniquely
            identified by path and SHA256 digest.
            Fields:
                digest (str): The SHA256 HEX digest.
            """

            TYPE = 'file'

            digest = models.TextField(null=False)

            class Meta:
                # Note the comma, this must be a tuple.
                unique_together = ('digest',)
                default_related_name = "%(app_label)s_%(model_name)s"

In this example the Content's uniqueness enforced on a single field ``digest``. For a multi-field
uniqueness, simply add other fields.

.. code-block:: python

        class FileContent(Content):
            """
            The "file" content type.
            Content of this type represents a single file uniquely
            identified by path and SHA256 digest.
            Fields:
                relative_path (str): The file relative path.
                digest (str): The SHA256 HEX digest.
            """

            TYPE = 'file'

            relative_path = models.TextField(null=False)
            digest = models.TextField(null=False)

            class Meta:
                default_related_name = "%(app_label)s_%(model_name)s"
                unique_together = (
                   'relative_path',
                   'digest',
                )


The example above ensures that content is unique on ``relative_path`` and ``digest`` together.

ForeignKey Gotchas
~~~~~~~~~~~~~~~~~~

The orphan cleanup operation performs mass-deletion of Content units that are not associated with
any repository. Any ForeignKey relationships that refer to Content with a deletion relationship of
``PROTECT`` will cause Orphan cleanup errors like::

    django.db.models.deletion.ProtectedError: ("Cannot delete some instances of model 'MyContent'
    because they are referenced through a protected foreign key: 'MyOtherContent.mycontent'"
