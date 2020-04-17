.. _subclassing_import-export:

Pulp Import/Export
==================

The Pulp Import/Export process is based around the `Django Import/Export library <https://django-import-export.readthedocs.io/en/latest/>`_ .
To be 'exportable/importable', your plugin must define a ``modelresource`` module at
``<plugin>/app/modelresource.py``. The module must contain a ModelResource subclasses
for each Model you want to expose, and it must define an ``IMPORT_ORDER`` ordered list
for all such ModelResources.

QueryModelResource
~~~~~~~~~~~~~~~~~~

If you don't need to do anything "special" to export your Model you can subclass
``QueryModelResource``. This only requires you to provide the ``Meta.model`` class for the
Model being export/imported, and to override the ``set_up_queryset(self)`` method to
define a limiting filter based on the self.repo_version provided by ``QueryModelResource``.

An example ``QueryModelResource`` subclasses, for import/exporting the ``Bar`` Model
from ``pulp_foo``, would look like this::

    class BarResource(QueryModelResource):
        """
        Resource for import/export of foo_bar entities
        """

        def set_up_queryset(self):
            """
            :return: Bars specific to a specified repo-version.
            """
            return Bar.objects.filter(pk__in=self.repo_version.content)

        class Meta:
            model = Bar


modelresource.py
~~~~~~~~~~~~~~~~

A simple ``modelresource.py`` module might look like this::

    from pulpcore.app.modelresource import QueryModelResource
    from pulp_file.app.models import FileContent

    class FileContentResource(QueryModelResource):
        """
        Resource for import/export of file_filecontent entities
        """

        def set_up_queryset(self):
            """
            :return: FileContents specific to a specified repo-version.
            """
            return FileContent.objects.filter(pk__in=self.repo_version.content)

        class Meta:
            model = FileContent


    IMPORT_ORDER = [FileContentResource]
