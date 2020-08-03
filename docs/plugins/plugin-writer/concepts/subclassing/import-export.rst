.. _subclassing_import-export:

Pulp Import/Export
==================

The Pulp Import/Export process is based around the `Django Import/Export library <https://django-import-export.readthedocs.io/en/latest/>`_ .
To be 'exportable/importable', your plugin must define a ``modelresource`` module at
``<plugin>/app/modelresource.py``. The module must contain a ModelResource subclass
for each Model you want to expose, and it must define an ``IMPORT_ORDER`` ordered list
for all such ModelResources.

QueryModelResource
~~~~~~~~~~~~~~~~~~

If you don't need to do anything "special" to export your Model you can subclass
``pulpcore.plugin.importexport.QueryModelResource``. This only requires you to provide the
``Meta.model`` class for the Model being export/imported, and to override the
``set_up_queryset(self)`` method to define a limiting filter. QueryModelResource is instantiated
by the export process with the RepositoryVersion being exported (``self.repo_version``).

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


BaseContentResource
~~~~~~~~~~~~~~~~~~~~

The ``BaseContentResource`` class provides a base class for exporting ``Content``.
``BaseContentResource`` provides extra functionality on top of ``QueryModelResource`` specific to
handling the exporting and importing of Content such as handling of Content-specific fields like
``upstream_id``.

An example of subclassing ``BaseContentResource`` looks like::

    class MyContentResource(BaseContentResource):
        """
        Resource for import/export of MyContent.
        """

        def set_up_queryset(self):
            """
            :return: MyContent specific to a specified repo-version.
            """
            return MyContent.objects.filter(pk__in=self.repo_version.content)

        class Meta:
            model = MyContent


modelresource.py
~~~~~~~~~~~~~~~~

A simple ``modelresource.py`` module is the one for the ``pulp_file`` plugin. It looks like
this::

    from pulpcore.plugin.importexport import BaseContentResource
    from pulp_file.app.models import FileContent

    class FileContentResource(BaseContentResource):
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


content_mapping
~~~~~~~~~~~~~~~

By default, all the Content that gets imported is automatically associated with the Repository it
is stored with inside the export archive. In some cases, this may not be desirable. One such case is
when there is Content that is tied to a sub_repo but not directly to the Repository itself. Another
case is where you may have Content you want imported but not associated with a Repositoy. In such
cases, you can set a ``content_mapping`` property on the Resource.

The ``content_mapping`` property should be a dictionary that maps repository names to a list of
content_ids. The importer code in pulp will combine the ``content_mappings`` across Resources and
export them to a ``content_mapping.json`` file that it will use during import to map Content to
Repositories.

Here is an example that deals with subrepos::

    class MyContentResource(BaseContentResource):
        """
        Resource for import/export of MyContent.
        """

        def __init__(self, *args, **kwargs):
            """Override __init__ to set content_mapping to a dict."""
            self.content_mapping = {}
            super().__init__(*args, **kwargs)

        def set_up_queryset(self):
            """Set up the queryset and our content_mapping."""
            content = MyContent.objects.filter(pk__in=self.repo_version.content)
            self.content_mapping[self.repository_version.repository.name] = content

            for repo in self.subrepos(self.repo_version):
                subrepo_content = repo.latest_repository_version.content
                self.content_mapping[repo.name] = subrepo_content
                content |= subrepo_content

            return content

        class Meta:
            model = MyContent

