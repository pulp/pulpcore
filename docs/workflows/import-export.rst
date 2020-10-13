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
    Pulp instance whose :term:`RepositoryVersions<RepositoryVersion>` we want to export
Downstream
    Pulp instance that will be importing those :term:`RepositoryVersions<RepositoryVersion>`
ModelResource
    entity that understands how to map the metadata for a specific Model
    owned/controlled by a plugin to an exportable file-format
    (see `django-import-export <https://django-import-export.readthedocs.io/en/latest/api_resources.html#modelresource>`_)
Exporter
    resource that exports content from Pulp for a variety of different use cases
PulpExporter
    kind-of Exporter, that is specifically used to export data from an Upstream
    for consumption by a Downstream
PulpExport
    specific instantiation/run of a PulpExporter
Export file
    compressed tarfile containing database content and :term:`Artifacts<Artifact>` for
    :term:`RepositoryVersions<RepositoryVersion>`, generated during execution of an Export
PulpImporter
    resource that accepts an Upstream PulpExporter export file, and manages
    the process of importing the content and :term:`Artifacts<Artifact>` included
PulpImport
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
    export ZOO_HREF=$(http POST :/pulp/api/v3/repositories/rpm/rpm/ name=zoo | jq -r '.pulp_href')
    #
    # add a remote
    http POST :/pulp/api/v3/remotes/rpm/rpm/ name=zoo url=https://fixtures.pulpproject.org/rpm-signed/  policy='immediate'
    #
    # find remote's href
    export REMOTE_HREF=$(http :/pulp/api/v3/remotes/rpm/rpm/ | jq -r ".results[] | select(.name == \"zoo\") | .pulp_href")
    #
    # sync the repository to give us some content
    http POST :$ZOO_HREF'sync/' remote=$REMOTE_HREF

Set up 'isofile' repository::

    # create the repository
    ISOFILE_HREF=$(http POST :/pulp/api/v3/repositories/file/file/ name=isofile | jq -r '.pulp_href')
    #
    # add remote
    http POST :/pulp/api/v3/remotes/file/file/ name=isofile url=https://fixtures.pulpproject.org/file/PULP_MANIFEST
    #
    # find remote's href
    REMOTE_HREF=$(http :/pulp/api/v3/remotes/file/file/ | jq -r ".results[] | select(.name == \"isofile\") | .pulp_href")
    #
    # sync the repository to give us some content
    http POST :$ISOFILE_HREF'sync/' remote=$REMOTE_HREF

Now that we have :term:`Repositories<Repository>` with content, let's define an Exporter named ``test-exporter``
that will export these :term:`Repositories<Repository>` to the directory ``/tmp/exports/``::

    export EXPORTER_HREF=$(http POST :/pulp/api/v3/exporters/core/pulp/ \
        name=test-exporter                                              \
        repositories:=[\"${ISOFILE_HREF}\",\"${ZOO_HREF}\"]             \
        path=/tmp/exports/ | jq -r '.pulp_href')
    http GET :${EXPORTER_HREF}

Exporting Content
-----------------

Once we have an Exporter defined, we invoke it to generate an export-file in the directory
specified by that Exporter's ``path`` attribute::

    http POST :${EXPORTER_HREF}exports/

The resulting Export writes to a ``.tar.gz`` file, in the directory pointed to by the
Exporter's path, with a name that follows the convention ``export-<export-UUID>-YYYYmmdd_HHMM.tar.gz``.

It will also produce a "table of contents" file describing the file (or files, see
`Exporting Chunked Files`_ below) for later use verifying and importing the results of the export::

    ls /tmp/exports
    export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000.tar.gz
    export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000-toc.json
    python -m json.tool /tmp/exports/export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000-toc.json
        {
        "meta": {
            "chunk_size": 0, # chunk_size in bytes, or 0 if an export did not use the chunk_size parameter
            "file": "export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000.tar.gz",
            "global_hash": "eaef962943915ecf6b5e45877b162364284bd9c4f367d9c96d18c408012ef424"
        },
        "files": {
            "export-32fd25c7-18b2-42de-b2f8-16f6d90358c3-20200416_2000.tar.gz": "eaef962943915ecf6b5e45877b162364284bd9c4f367d9c96d18c408012ef424"
        }
    }

These export files can now be transferred to a Downstream Pulp instance, and imported.

.. note::

   In the event of any failure during an export, the process will clean up any partial
   export-files that may have been generated. Export-files can be very large; this will
   preserve available space in the export-directory.

Exporting Specific Versions
---------------------------

By default, the latest-versions of the :term:`Repositories<Repository>` specified in the Exporter are exported. However, you
can export specific :term:`RepositoryVersions<RepositoryVersion>` of those :term:`Repositories<Repository>`
if you wish using the ``versions=`` parameter on the ``/exports/`` invocation.

Following the above example - let's assume we want to export the "zero'th" :term:`RepositoryVersion` of the
repositories in our Exporter.::

    http POST :${EXPORTER_HREF}exports/ \
        versions:=[\"${ISO_HREF}versions/0/\",\"${ZOO_HREF}versions/0/\"]

Note that the "zero'th" :term:`RepositoryVersion` of a :term:`Repository` is created when the :term:`Repository` is created, and is empty. If you unpack the resulting Export ``tar.gz`` you will find, for example, that there is no ``artifacts/`` directory and an empty ``ArtifactResource.json`` file::

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

Exporting Incrementally
-----------------------

By default, PulpExport exports all of the content and artifacts of the
:term:`RepositoryVersions<RepositoryVersion>` being exported. A common use-case is to do
regular transfers of content from an Upstream to a Downstream Pulp instance.  While you
**can** export everything every time, it is an inefficient use of time and disk storage to
do so; exporting only the "entities that have changed" is a better choice. You can
accomplish this by setting the ``full`` parameter on the ``/exports/`` invocation to
``False``::

    http POST :${EXPORTER_HREF}exports/ full=False

This results in an export of all content-entities, but only :term:`Artifacts<Artifact>`
that have been **added** since the `last_export` of the same Exporter.

You can override the use of `last_export` as the starting point of an incremental export by use of the ``start_versions=``
parameter. Building on our example Exporter, if we want to do an incremental export of everything that's happened since the
**second** :term:`RepositoryVersion` of each :term:`Repository`, regardless of what happened in our last export,
we would issue a command such as the following::

    http POST :${EXPORTER_HREF}exports/ \
        full=False                      \
        start_versions:=[\"${ISO_HREF}versions/1/\",\"${ZOO_HREF}versions/1/\"]

This would produce an incremental export of everything that had been added to our :term:`Repositories<Repository>`
between :term:`RepositoryVersion` '1' and the ``current_version`` :term:`RepositoryVersions<RepositoryVersion>`
of our :term:`Repositories<Repository>`.

Finally, if we need complete comtrol over incremental exporting, we can combine the use of ``start_versions=`` and ``versions=``
to produce an incremental export of everything that happened after ``start_versions=`` up to and including ``versions=``::

    http POST :${EXPORTER_HREF}exports/                                         \
        full=False                                                              \
        start_versions:=[\"${ISO_HREF}versions/1/\",\"${ZOO_HREF}versions/1/\"] \
        versions:=[\"${ISO_HREF}versions/3/\",\"${ZOO_HREF}versions/3/\"]

.. note::

    **Note** that specifying ``start_versions=`` without specifying ``full=False`` (i.e., asking for an incremental export)
    is an error, since it makes no sense to specify a 'starting version' for a full export.

Exporting Chunked Files
-----------------------

By default, PulpExport streams data into a single ``.tar.gz`` file. Since :term:`Repositories<Repository>`
can contain a lot of artifacts and content, that can result in a file too large to be
copied to transport media. In this case, you can specify a maximum-file-size, and the
export process will chunk the tar.gz into a series of files no larger than this.

You accomplish this by setting the ``chunk_size`` parameter to the desired maximum number of bytes. This
parameter takes an integer, or size-units of KB, MB, or GB. Files appear in the Exporter.path
directory, with a four-digit sequence number suffix::

    http POST :/pulp/api/v3/exporters/core/pulp/1ddbe6bf-a6c3-4a88-8614-ad9511d21b94/exports/ chunk_size="10KB"
        {
            "task": "/pulp/api/v3/tasks/da3350f7-0102-4dd5-81e0-81becf3ffdc7/"
        }
    ls -l /tmp/exports/
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0000
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0001
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0002
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0003
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0004
        10K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0005
        2.3K export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0006
        1168 export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325-toc.json

The "table of contents" lists all the resulting files and their checksums::

    python -m json.tool /tmp/exports/export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325-toc.json
    {
        "meta": {
            "chunk_size": 10240,
            "file": "export-8c1891a3-ffb5-41a7-b141-51daa0e38a18-20200717_1947.tar.gz",
            "global_hash": "eaef962943915ecf6b5e45877b162364284bd9c4f367d9c96d18c408012ef424"
        },
        "files": {
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0000": "8156874798802f773bcbaf994def6523888922bde7a939bc8ac795a5cbb25b85",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0001": "e52fac34b0b7b1d8602f5c116bf9d3eb5363d2cae82f7cc00cc4bd5653ded852",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0002": "df4a2ea551ff41e9fb046e03aa36459f216d4bcb07c23276b78a96b98ae2b517",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0003": "27a6ecba3cc51965fdda9ec400f5610ff2aa04a6834c01d0c91776ac21a0e9bb",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0004": "f35c5a96fccfe411c074463c0eb0a77b39fa072ba160903d421c08313aba58f8",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0005": "13458b10465b01134bde49319d6b5cba9948016448da9d35cb447265a25e3caa",
            "export-780822a4-d280-4ed0-a53c-382a887576a6-20200522_2325.tar.gz.0006": "a1986a0590943c9bb573c7d7170c428457ce54efe75f55997259ea032c585a35"
        }
    }

Updating an Exporter
--------------------

You can update an Exporter to modify a subset of its fields::

    http PATCH :${EXPORTER_HREF} path=/tmp/newpath

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


After the importer is created, a POST request to create an import will trigger the import process.

You can import an exported ``.tar.gz`` directly using the ``path`` parameter::

    http POST :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/ \
      path="/data/export-113c8950-072b-432a-9da6-24da1f4d0a02-20200408_2015.tar.gz"

Or you can point the importer at the "table of contents" file that was produced by an export.
If the TOC file is in the same directory as the export-files it points to, the import process
will:

    * verify the checksum(s) of all export-files,
    * reassemble a chunked-export into a single ``.tar.gz``
    * remove chunks as they are used (in order to conserve disk space)
    * verify the checksum of the resulting reassembled ``.tar.gz``

and then import the result::

    http POST :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/ \
      toc="/data/export-113c8950-072b-432a-9da6-24da1f4d0a02-20200408_2015-toc.json"

.. note::

    The directory containing the file pointed to by ``path`` or ``toc`` must be defined in the
    ``ALLOWED_IMPORT_PATHS`` setting or the import will fail.

The command to create an import will return a task that can be used to monitor the import. You can
also see a history of past imports::

    http :/pulp/api/v3/importers/core/pulp/f8acba87-0250-4640-b56b-c92597d344b7/imports/
