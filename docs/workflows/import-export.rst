Pulp Import and Export
======================

.. warning::
    Support for import and export is provided as a tech preview in Pulp 3. Functionality may not
    work or may be incomplete. Also, backwards compatibility when upgrading is not guaranteed.

Overview
^^^^^^^^

There is a use-case for extracting the content and :term:`Artifacts<Artifact>` for a set of
:term:`RepositoryVersions<RepositoryVersion>`, out of a running instance of Pulp and into
a file that can then be transferred to another Pulp instance and imported. This is not
the Pulp-to-Pulp sync case; the assumption is that the receiving Pulp instance is
network-isolated.

The high-level workflow for this use case is

1. On the Upstream Pulp instance, an Exporter is defined for the set of
:term:`Repositories<Repository>` that are to be exported to some Downstream Pulp instance.

2. That Exporter is requested to produce and execute an Export for the current
:term:`RepositoryVersions<RepositoryVersion>` of the specified
:term:`Repositories<Repository>`

3. The resulting ``.tar.gz`` Export is transferred to the appropriate Downstream.

4. On the Downstream Pulp instance, an Importer is defined, that maps the incoming
Upstream :term:`Repositories<Repository>` to matching Downstream
:term:`Repositories<Repository>`.

5. That Importer is requested to produce and execute an Import, pointing to the provided
export file from the Upstream.

In order to minimize space utilization, import/export operates on sets of
:term:`Repositories<Repository>`. This allows the Export operation to export shared
:term:`Artifacts<Artifact>` only once per-export, rather than once for each
:term:`Repository` being exported.

.. note::

    Export will not operate on :term:`RepositoryVersions<RepositoryVersion>` that have
    been synchronized using ``policy=on_demand``. :term:`Artifacts<Artifact>` must actually
    exist in order to be exported - this is, after all the only way for the Downstream Pulp
    instance to gain access to them!

.. note::

    Import and Export strictly control which directories may be read from/written to via
    the settings options ``ALLOWED_IMPORT_PATHS`` and ``ALLOWED_EXPORT_PATHS``.
    These default to empty, if not explicitly set attempts to import or export will fail
    with a validation error like

        ``"Path '/tmp/exports/' is not an allowed export path"``

Definitions
^^^^^^^^^^^
Upstream
    Pulp instance whose :term:`RepositoryVersion(s)<RepositoryVersion>` we want to export
Downstream
    Pulp instance that will be importing those :term:`RepositoryVersion(s)<RepositoryVersion>`
ModelResource
    entity that understands how to map the metadata for a specific model
    owned/controlled by a plugin to an exportable file-format (see django-import-export)
Exporter
    resource that exports content from Pulp for a variety of different use cases
PulpExporter
    kind-of Exporter, that is specifically used to export data from an Upstream
    for consumption by a Downstream
Export
    specific instantiation/run of a PulpExporter
Export file
    compressed tarfile containing database content and :term:`Artifacts<Artifact>` for
    :term:`RepositoryVersions<RepositoryVersion>`, generated during execution of an Export
PulpImporter
    resource that accepts an Upstream PulpExporter export file, and manages
    the process of importing the content and :term:`Artifacts<Artifact>` included
Import
    specific instantiation/run of a PulpImporter
Repository-mapping
    configuration file that provides the ability to map an Upstream :term:`Repository`,
    to a Downstream :term:`Repository`, into which the Upstream’s :term:`RepositoryVersion`
    should be imported by a PulpImporter
Import order
    for complicated repository-types, managing relationships requires that
    ModelResources be imported in order. Plugins are responsible for specifying the
    import-order of the ModelResources they own

Exporting
^^^^^^^^^

.. note::

    The following examples assume a Pulp instance that includes the ``pulp_file`` and
    ``pulp_rpm`` plugins. They also assume that the ``http`` and ``jq`` packages are
    installed.

These workflows are executed on an Upstream Pulp instance.

Creating an Exporter
--------------------

In this workflow, you define an Exporter for a set of :term:`Repositories<Repository>`.
This Exporter can be invoked repeatedly to regularly export the current
:term:`RepositoryVersion` of each of the specified :term:`Repositories<Repository>`.

First, let's make a pair of :term:`Repositories<Repository>` named ``zoo`` and ``isofile``,
and save their UUIDs as ``ZOO_UUID`` and ``ISOFILE_UUID``

Set up 'zoo' repository"::

    # Create the repository
    export ZOO_HREF=$(http POST http://localhost:24817/pulp/api/v3/repositories/rpm/rpm/ name=zoo | jq -r '.pulp_href')
    #
    # add a remote
    http POST http://localhost:24817/pulp/api/v3/remotes/rpm/rpm/ name=zoo url=https://repos.fedorapeople.org/pulp/pulp/fixtures/rpm/  policy='immediate'
    #
    # find remote's href
    export REMOTE_HREF=$(http http://localhost:24817/pulp/api/v3/remotes/rpm/rpm/ | jq -r ".results[] | select(.name == \"zoo\") | .pulp_href")
    #
    # sync the repository to give us some content
    http POST http://localhost:24817$ZOO_HREF'sync/' remote=$REMOTE_HREF

Set up 'isofile' repository::

    # create the repository
    ISOFILE_HREF=$(http POST http://localhost:24817/pulp/api/v3/repositories/file/file/ name=isofile | jq -r '.pulp_href')
    #
    # add remote
    http POST http://localhost:24817/pulp/api/v3/remotes/file/file/ name=isofile url=https://repos.fedorapeople.org/pulp/pulp/fixtures/file/PULP_MANIFEST
    #
    # find remote's href
    REMOTE_HREF=$(http http://localhost:24817/pulp/api/v3/remotes/file/file/ | jq -r ".results[] | select(.name == \"isofile\") | .pulp_href")
    #
    # sync the repository to give us some content
    http POST http://localhost:24817$ISOFILE_HREF'sync/' remote=$REMOTE_HREF

Now that we have Repositories with content, let's define an Exporter named ``test-exporter``
that will export these Repositories to the directory ``/tmp/exports/``::

    export EXPORTER_HREF=$(http POST http://localhost:24817/pulp/api/v3/exporters/core/pulp/ name=test-exporter repositories:=[\"${ISOFILE_HREF}\",\"${ZOO_HREF}\"] path=/tmp/exports/ | jq -r '.pulp_href')
    http GET http://localhost:24817${EXPORTER_HREF}

Exporting Content
-----------------

Once we have an Exporter defined, we invoke it to generate an export-file in the directory
specified by that Exporter's ``path`` attribute::

    http POST http://localhost:24817${EXPORTER_HREF}exports/

The resulting Export writes to a ``.tar.gz`` file, in the directory pointed to by the
Exporter's path, with a name that follows the convention ``export-<export-UUID>-YYYYmmdd_HHMM.tar.gz``::

    ls /tmp/exports
    export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000.tar.gz

This export file can now be transferred to a Downstream Pulp instance, and imported.

Exporting Specific Versions
---------------------------

By default, the latest-versions of the Repositories specified in the Exporter are exported. However, you
can export specific RepositoryVersions of those Repositories if you wish using the ``versions`` parameter
on the ``/exports/`` ivovcation.

Following the above example - let's assume we want to export the "zero'th" RepositoryVersion of the
repositories in our Exporter.::

    http POST http://localhost:24817${EXPORTER_HREF}exports/ versions:=[\"${ISO_HREF}versions/0/\",\"${ZOO_HREF}versions/0/\"]

Note that the "zero'th" RepositoryVersion of a Repository is created when the Repository is created, and is empty. If you unpack the resulting Export ``tar.gz`` you will find, for example, that there is no ``artifacts/`` directory and an empty ``ArtifactResource.json`` file::

    cd /tmp/exports
    tar xvzf export-930ea60c-97b7-4e00-a737-70f773ebbb14-20200511_2005.tar.gz
        versions.json
        pulpcore.app.modelresource.ArtifactResource.json
        pulpcore.app.modelresource.RepositoryResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulpcore.app.modelresource.ContentResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulpcore.app.modelresource.ContentArtifactResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.PackageResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.ModulemdResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.ModulemdDefaultsResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.PackageGroupResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.PackageCategoryResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.PackageEnvironmentResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.PackageLangpacksResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.UpdateRecordResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.DistributionTreeResource.json
        repository-3c1ec06a-b0d6-4d04-9f99-32bfc0a499a9_0/pulp_rpm.app.modelresource.RepoMetadataFileResource.json
        repository-958ae747-c19d-4820-828c-87452f1a5b8d_0/pulpcore.app.modelresource.ContentResource.json
        repository-958ae747-c19d-4820-828c-87452f1a5b8d_0/pulpcore.app.modelresource.ContentArtifactResource.json
        repository-958ae747-c19d-4820-828c-87452f1a5b8d_0/pulp_file.app.modelresource.FileContentResource.json
    python -m json.tool pulpcore.app.modelresource.ArtifactResource.json
        []

Updating an Exporter
--------------------

You can update an Exporter to modify a subset of its fields::

    http PATCH http://localhost:24817${EXPORTER_HREF} path=/tmp/newpath

Importing
^^^^^^^^^

Creating the importer
---------------------

The first step to importing a Pulp export archive is to create an importer::

    http :/pulp/api/v3/importers/core/pulp/ name="test"


By default, Pulp will map :term:`Repositories<Repository>` in the export to :term:`Repositories<Repository>`
in Pulp by name. This can be overriden by supplying a repo mapping that maps names from the Pulp export
to the names of repos in Pulp. For example, suppose the name of the repo in the Pulp export achive was
'source' and the repo in Pulp was 'dest'. The following command would set up this mapping::

    http :/pulp/api/v3/importers/core/pulp/ name="test" repo_mapping:="{\"source\": \"dest\"}"


After the importer is created, a POST request to create an import will trigger the import process::

    http POST :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/ \
      path="/data/export-113c8950-072b-432a-9da6-24da1f4d0a02-20200408_2015.tar.gz"


One thing worth noting is that the path must be defined in the ``ALLOWED_IMPORT_PATHS`` setting.

The command to create an import will return a task that can be used to monitor the import. You can
also see a history of past imports::

    http :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/
