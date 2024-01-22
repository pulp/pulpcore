Adding and Removing Content
===========================

For adding and removing content, Pulp 3 provides a layered plugin API. The docs below explain our
lower level API; this information is helpful to understand how a synchronize task works under the
hood.

Repository Versions
-------------------

Starting with Pulp 3, repositories are versioned. A new immutable respository version is created
when its set of content units changes

To facilitate the creation of repository versions a
`pulpcore.plugin.models.RepositoryVersion` context manager is provided. Plugin Writers are
strongly encouraged to use RepositoryVersion as a context manager to provide transactional safety,
working directory setup, and database cleanup after encountering failures.

.. code-block:: python

     with repository.new_version() as new_version:

        # add content manually
        new_version.add_content(content)
        new_version.remove_content(content)

.. warning::

    Any action that adds/removes content to a repository *must* create a new RepositoryVersion.
    Every action that creates a new RepositoryVersion *must* be asynchronous (defined as a task).
    Task reservations are necessary to prevent race conditions.

.. _sync-docs:

Synchronizing
-------------

.. tip::

    Please consider using the high level :ref:`stages-concept-docs` for actual implementations.

Most plugins will define a synchronize task, which fetches content from a remote repository, and
adds it to a Pulp repository.

A typical synchronization task will follow this pattern:

* Download and analyze repository metadata from a remote source.
* Decide what needs to be added to repository or removed from it.
* Associate already existing content to a repository by creating an instance of
  :class:`~pulpcore.plugin.models.RepositoryContent` and saving it.
* Remove :class:`~pulpcore.plugin.models.RepositoryContent` objects which were identified for
  removal.
* For every content which should be added to Pulp create but do not save yet:

  * instance of ``ExampleContent`` which will be later associated to a repository.
  * instance of :class:`~pulpcore.plugin.models.ContentArtifact` to be able to create relations with
    the artifact models.
  * instance of :class:`~pulpcore.plugin.models.RemoteArtifact` to store information about artifact
    from remote source and to make a relation with :class:`~pulpcore.plugin.models.ContentArtifact`
    created before.

* If a remote content should be downloaded right away (aka ``immediate`` download policy), use
  the suggested  :ref:`downloading <download-docs>` solution. If content should be downloaded
  later (aka ``on_demand`` or ``background`` download policy), feel free to skip this step.
* Save all artifact and content data in one transaction:

  * in case of downloaded content, create an instance of
    :class:`~pulpcore.plugin.models .Artifact`. Set the `file` field to the
    absolute path of the downloaded file. Pulp will move the file into place
    when the Artifact is saved. The Artifact refers to a downloaded file on a
    filesystem and contains calculated checksums for it.
  * in case of downloaded content, update the :class:`~pulpcore.plugin.models.ContentArtifact` with
    a reference to the created :class:`~pulpcore.plugin.models.Artifact`.
  * create and save an instance of the :class:`~pulpcore.plugin.models.RepositoryContent` to
    associate the content to a repository.
  * save all created artifacts and content: ``ExampleContent``,
    :class:`~pulpcore.plugin.models.ContentArtifact`,
    :class:`~pulpcore.plugin.models.RemoteArtifact`.

* Use :class:`~pulpcore.plugin.models.ProgressReport` to report the progress of some steps if needed.
