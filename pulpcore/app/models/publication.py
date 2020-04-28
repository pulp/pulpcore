from django.db import IntegrityError, models, transaction

from .base import MasterModel, BaseModel
from .content import Artifact, Content, ContentArtifact
from .repository import Remote, Repository, RepositoryVersion
from .task import CreatedResource
from pulpcore.app.files import PulpTemporaryUploadedFile


class Publication(MasterModel):
    """
    A publication contains metadata and artifacts associated with content
    contained within a RepositoryVersion.

    Using as a context manager is highly encouraged.  On context exit, the complete attribute
    is set True provided that an exception has not been raised.  In the event and exception
    has been raised, the publication is deleted.

    Fields:
        complete (models.BooleanField): State tracking; for internal use. Indexed.
        pass_through (models.BooleanField): Indicates that the publication is a pass-through
            to the repository version. Enabling pass-through has the same effect as creating
            a PublishedArtifact for all of the content (artifacts) in the repository.

    Relations:
        repository_version (models.ForeignKey): The RepositoryVersion used to
            create this Publication.

    Examples:
        >>> repository_version = ...
        >>>
        >>> with Publication.create(repository_version) as publication:
        >>>     for content in repository_version.content():
        >>>         for content_artifact in content.contentartifact_set.all():
        >>>             artifact = PublishedArtifact(...)
        >>>             artifact.save()
        >>>             metadata = PublishedMetadata.create_from_file(...)
        >>>             ...
        >>>
    """

    TYPE = "publication"

    complete = models.BooleanField(db_index=True, default=False)
    pass_through = models.BooleanField(default=False)

    repository_version = models.ForeignKey("RepositoryVersion", on_delete=models.CASCADE)

    @classmethod
    def create(cls, repository_version, pass_through=False):
        """
        Create a publication.

        This should be used to create a publication.  Using Publication() directly
        is highly discouraged.

        Args:
            repository_version (pulpcore.app.models.RepositoryVersion): The repository
                version to be published.
            pass_through (bool): Indicates that the publication is a pass-through
                to the repository version. Enabling pass-through has the same effect
                as creating a PublishedArtifact for all of the content (artifacts)
                in the repository.

        Returns:
            pulpcore.app.models.Publication: A created Publication in an incomplete state.

        Notes:
            Adds a Task.created_resource for the publication.
        """
        with transaction.atomic():
            publication = cls(pass_through=pass_through, repository_version=repository_version)
            publication.save()
            resource = CreatedResource(content_object=publication)
            resource.save()
            return publication

    @property
    def repository(self):
        """
        Return the associated repository

        Returns:
            pulpcore.app.models.Repository: The repository associated to this publication
        """
        return self.repository_version.repository

    def delete(self, **kwargs):
        """
        Delete the publication.

        Args:
            **kwargs (dict): Delete options.

        Notes:
            Deletes the Task.created_resource when complete is False.
        """
        with transaction.atomic():
            CreatedResource.objects.filter(object_id=self.pk).delete()
            super().delete(**kwargs)

    def finalize_new_publication(self):
        """
        Finalize the incomplete Publication with plugin-provided code.

        This method should be overridden by plugin writers for an opportunity for plugin input. This
        method is intended to be used to validate or modify the content.

        This method does not adjust the value of complete, or save the `Publication` itself.
        Its intent is to allow the plugin writer an opportunity for plugin input before pulpcore
        marks the `Publication` as complete.
        """
        pass

    def __enter__(self):
        """
        Enter context.

        Returns:
            Publication: self
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Set the complete=True, create the publication.

        Args:
            exc_type (Type): (optional) Type of exception raised.
            exc_val (Exception): (optional) Instance of exception raised.
            exc_tb (types.TracebackType): (optional) stack trace.
        """
        if exc_val:
            self.delete()
        else:
            try:
                self.finalize_new_publication()
                self.complete = True
                self.save()
            except Exception:
                self.delete()
                raise


class PublishedArtifact(BaseModel):
    """
    An artifact that is part of a publication.

    Fields:
        relative_path (models.TextField): The (relative) path component of the published url.

    Relations:
        content_artifact (models.ForeignKey): The referenced content artifact.
        publication (models.ForeignKey): The publication in which the artifact is included.
    """

    relative_path = models.TextField()

    content_artifact = models.ForeignKey("ContentArtifact", on_delete=models.CASCADE)
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)

    class Meta:
        default_related_name = "published_artifact"
        unique_together = ("publication", "relative_path")


class PublishedMetadata(Content):
    """
    Metadata file that is part of a publication.

    Fields:
        relative_path (models.TextField): The (relative) path component of the published url.

    Relations:
        publication (models.ForeignKey): The publication in which the artifact is included.
    """

    TYPE = "publishedmetadata"

    relative_path = models.TextField()

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE)

    @classmethod
    def create_from_file(cls, file, publication, relative_path=None):
        """
        Creates PublishedMetadata along with Artifact, ContentArtifact, and PublishedArtifact.

        Args:
            file (django.core.files.File): an open File that contains metadata
            publication (pulpcore.app.models.Publication): The publication in which the
                PublishedMetadata is included.
            relative_path (str): relative path at which the Metadata is published at. If None, the
                name of the 'file' is used.

        Returns:
            PublishedMetadata (pulpcore.app.models.PublishedMetadata):
                A saved instance of PublishedMetadata.
        """

        with transaction.atomic():
            artifact = Artifact.init_and_validate(file=PulpTemporaryUploadedFile.from_file(file))
            try:
                with transaction.atomic():
                    artifact.save()
            except IntegrityError:
                artifact = Artifact.objects.get(sha256=artifact.sha256)
            if not relative_path:
                relative_path = file.name
            content = cls(relative_path=relative_path, publication=publication)
            content.save()
            ca = ContentArtifact(relative_path=relative_path, content=content, artifact=artifact)
            ca.save()
            pa = PublishedArtifact(
                relative_path=relative_path, content_artifact=ca, publication=publication
            )
            pa.save()
        return content

    class Meta:
        default_related_name = "published_metadata"
        unique_together = ("publication", "relative_path")


class ContentGuard(MasterModel):
    """
    Defines a named content guard.

    This is meant to be subclassed by plugin authors as an opportunity to provide
    plugin-specific persistent attributes and additional validation for those attributes.
    The permit() method must be overridden to provide the web request authorization logic.

    This object is a Django model that inherits from :class: `pulpcore.app.models.ContentGuard`
    which provides the platform persistent attributes for a content-guard. Plugin authors can
    add additional persistent attributes by subclassing this class and adding Django fields.
    We defer to the Django docs on extending this model definition with additional fields.

    Fields:
        name (models.TextField): Unique guard name.
        description (models.TextField): An optional description.

    """

    name = models.TextField(db_index=True, unique=True)
    description = models.TextField(null=True)

    def permit(self, request):
        """
        Authorize the specified web request.

        Args:
            request (django.http.HttpRequest): A request for a published file.

        Raises:
            PermissionError: When not authorized.
        """
        raise NotImplementedError()


class BaseDistribution(MasterModel):
    """
    A distribution defines how a publication is distributed by the Content App.

    This abstract model can be used by plugin writers to create concrete distributions that are
    stored in separate tables from the Distributions provided by pulpcore.

    The `name` must be unique.

    The ``base_path`` must have no overlapping components. So if a Distribution with ``base_path``
    of ``a/path/foo`` existed, you could not make a second Distribution with a ``base_path`` of
    ``a/path`` or ``a`` because both are subpaths of ``a/path/foo``.

    Fields:
        name (models.TextField): The name of the distribution. Examples: "rawhide" and "stable".
        base_path (models.TextField): The base (relative) path component of the published url.

    Relations:
        content_guard (models.ForeignKey): An optional content-guard.
        remote (models.ForeignKey): A remote that the content app can use to find content not
            yet stored in Pulp.
    """

    name = models.TextField(db_index=True, unique=True)
    base_path = models.TextField(unique=True)

    content_guard = models.ForeignKey(ContentGuard, null=True, on_delete=models.SET_NULL)
    remote = models.ForeignKey(Remote, null=True, on_delete=models.SET_NULL)

    def content_handler(self, path):
        """
        Handler to serve extra, non-Artifact content for this Distribution

        Args:
            path (str): The path being requested
        Returns:
            None if there is no content to be served at path. Otherwise a
            aiohttp.web_response.Response with the content.
        """
        return None

    def content_handler_list_directory(self, rel_path):
        """
        Generate the directory listing entries for content_handler

        Args:
            rel_path (str): relative path inside the distribution's base_path. For example,
            the root of the base_path is '', a subdir within the base_path is 'subdir/'.
        Returns:
            Set of strings for the extra entries in rel_path
        """
        return set()


class PublicationDistribution(BaseDistribution):
    """
    Define how Pulp's content app will serve a Publication.

    Relations:
        publication (models.ForeignKey): Publication to be served.
    """

    publication = models.ForeignKey(Publication, null=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True


class RepositoryVersionDistribution(BaseDistribution):
    """
    Define how Pulp's content app will serve a RepositoryVersion or Repository.

    The ``repository`` and ``repository_version`` fields cannot be used together.

    Relations:
        repository (models.ForeignKey): The latest RepositoryVersion for this Repository will be
            served.
        repository_version (models.ForeignKey): RepositoryVersion to be served.
    """

    repository = models.ForeignKey(Repository, null=True, on_delete=models.SET_NULL)
    repository_version = models.ForeignKey(RepositoryVersion, null=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True
