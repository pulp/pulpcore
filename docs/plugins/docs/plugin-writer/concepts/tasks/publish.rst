Publish
=======

In order to make content files available to clients, users must publish these files. Typically,
users will publish a repository which will make the content in the repository available.

When publishing a repository, your plugin needs to mimic the layout of both data and metadata. In
the simplest case for content types that don't have metadata, only the content unit data itself
needs to be published.

In most cases, both metadata and content unit data are required to make a usable publication. It's
important to understand what the required metadata is for your content type.

**Using a** :class:`~pulpcore.plugin.models.Publication` **context manager is highly encouraged.**  On
context exit, the complete attribute is set True provided that an exception has not been raised.
In the event an exception has been raised, the publication is deleted.

One of the ways to perform publishing:

* Find :class:`~pulpcore.plugin.models.ContentArtifact` objects which should be published
* For each of them create and save instance of :class:`~pulpcore.plugin.models.PublishedArtifact`
  which refers to :class:`~pulpcore.plugin.models.ContentArtifact` and
  :class:`~pulpcore.app.models.Publication` to which this artifact belongs.
* Generate and write to disk repository metadata
* For each of the metadata files create an instance of
  :class:`~pulpcore.plugin.models.PublishedMetadata` using `create_from_file` constructor. Each
  instance relates a metadata file to a :class:`~pulpcore.app.models.Publication`.
* Use :class:`~pulpcore.plugin.models.ProgressReport` to report progress of some steps if needed.
