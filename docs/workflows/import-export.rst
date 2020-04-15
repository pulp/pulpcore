Import and Export
=================

.. warning::
    Support for import and export is provided as a tech preview in Pulp 3. Functionality may not
    work or may be incomplete. Also, backwards compatibility when upgrading is not guaranteed.



Importing
^^^^^^^^^

Creating the importer
---------------------

The first step to importing a Pulp export archive is to create an importer::

    http :/pulp/api/v3/importers/core/pulp/ name="test"


By default, Pulp will map repositories in the export to repositories in Pulp by name. This can be
overriden by supplying a repo mapping that maps names from the Pulp export to the names of repos in
Pulp. For example, suppose the name of the repo in the Pulp export achive was 'source' and the repo
in Pulp was 'dest'. The following command would set up this mapping::

    http :/pulp/api/v3/importers/core/pulp/ name="test" repo_mapping:="{\"source\": \"dest\"}"


After the importer is created, a POST request to create an import will trigger the import process::

    http POST :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/ \
      path="/data/export-113c8950-072b-432a-9da6-24da1f4d0a02-20200408_2015.tar.gz"


One thing worth noting is that the path must be defined in the ``ALLOWED_IMPORT_PATHS`` setting.

The command to create an import will return a task that can be used to monitor the import. You can
also see a history of past imports::

    http :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/
