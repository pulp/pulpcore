import hashlib
import os
import re
from datetime import timedelta
from url_normalize import url_normalize
from urllib.parse import urlparse, urljoin

from aiohttp.web_exceptions import HTTPNotFound

from django.conf import settings
from django.contrib.postgres.fields import HStoreField
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django_lifecycle import hook, AFTER_UPDATE, BEFORE_DELETE

from .base import MasterModel, BaseModel
from .content import Artifact, Content, ContentArtifact
from .repository import Remote, Repository, RepositoryVersion
from .task import CreatedResource
from pulpcore.app.files import PulpTemporaryUploadedFile
from pulpcore.cache import Cache
from rest_framework.exceptions import APIException
from pulpcore.app.models import AutoAddObjPermsMixin
from pulpcore.responses import ArtifactResponse
from pulpcore.app.util import get_domain_pk, cache_key


class PublicationQuerySet(models.QuerySet):
    """A queryset that provides publication filtering methods."""

    def with_content(self, content):
        """
        Filters publictions that contain the provided content units.

        Args:
            content (django.db.models.QuerySet): query of content

        Returns:
            django.db.models.QuerySet: Publications that contain content.
        """
        pub_artifact_q = Publication.objects.filter(
            published_artifact__content_artifact__content__pk__in=content
        )
        pass_thru_q = Publication.objects.filter(
            pass_through=True,
            repository_version__pk__in=RepositoryVersion.objects.with_content(content),
        )

        return pub_artifact_q | pass_thru_q


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
        pulp_domain (models.ForeignKey): The domain the Publication is a part of.

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

    objects = PublicationQuerySet.as_manager()

    complete = models.BooleanField(db_index=True, default=False)
    pass_through = models.BooleanField(default=False)

    repository_version = models.ForeignKey("RepositoryVersion", on_delete=models.CASCADE)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

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
            # invalidate cache
            if settings.CACHE_ENABLED:
                # Find any publications being served directly
                base_paths = self.distribution_set.values_list("base_path", flat=True)
                # Find any publications being served indirectly by auto-distribute feature
                # It's possible for errors to occur before any publication has been completed,
                # so we need to handle the case when no Publication exists.
                try:
                    versions = self.repository.versions.all()
                    pubs = Publication.objects.filter(
                        repository_version__in=versions, complete=True
                    )
                    publication = pubs.latest("repository_version", "pulp_created")
                    if self.pk == publication.pk:
                        base_paths |= self.repository.distributions.values_list(
                            "base_path", flat=True
                        )
                except Publication.DoesNotExist:
                    pass

                # Invalidate cache for all distributions serving this publication
                if base_paths:
                    Cache().delete(base_key=cache_key(base_paths))

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
            # If an exception got us here, the Publication we were trying to create is
            # Bad, and we should delete the attempt. HOWEVER - some exceptions happen before we
            # even get that far. In those cases, calling delete() results in a new not-very-useful
            # exception being raised and reported to the user, rather than the actual problem.
            try:
                self.delete()
            except Exception:
                raise exc_val.with_traceback(exc_tb)
        else:
            try:
                self.finalize_new_publication()
                self.complete = True
                self.save()
            except Exception:
                self.delete()
                raise

            # invalidate cache
            if settings.CACHE_ENABLED:
                base_paths = Distribution.objects.filter(
                    repository=self.repository_version.repository
                ).values_list("base_path", flat=True)
                if base_paths:
                    base_keys = [f"{self.pulp_domain.name}:{base_path}" for base_path in base_paths]
                    Cache().delete(base_key=base_keys)


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
        domain = publication.pulp_domain
        with transaction.atomic():
            artifact = Artifact.init_and_validate(file=PulpTemporaryUploadedFile.from_file(file))
            try:
                with transaction.atomic():
                    artifact.save()
            except IntegrityError:
                artifact = Artifact.objects.get(sha256=artifact.sha256, pulp_domain=domain)
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
        name (models.TextField): Unique guard name per domain.
        description (models.TextField): An optional description.
        pulp_domain (models.ForeignKey): The domain the ContentGuard is a part of.

    """

    name = models.TextField(db_index=True)
    description = models.TextField(null=True)
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)

    def permit(self, request):
        """
        Authorize the specified web request.

        Args:
            request (aiohttp.web.Request): A request for a published file.

        Raises:
            PermissionError: When not authorized.
        """
        raise NotImplementedError()

    @hook(BEFORE_DELETE)
    def invalidate_cache(self):
        if settings.CACHE_ENABLED:
            base_paths = self.distribution_set.values_list("base_path", flat=True)
            if base_paths:
                Cache().delete(base_key=cache_key(base_paths))

    class Meta:
        unique_together = ("name", "pulp_domain")


class RBACContentGuard(ContentGuard, AutoAddObjPermsMixin):
    """
    A content guard that protects content based on RBAC permissions.
    """

    TYPE = "rbac"

    def permit(self, request):
        """
        Authorize the specified web request. Expects the request to have already been authenticated.
        """
        if not (drequest := request.get("drf_request", None)):
            raise PermissionError("Content app didn't properly authenticate this request")
        from pulpcore.app.viewsets import RBACContentGuardViewSet

        view = RBACContentGuardViewSet()
        setattr(view, "get_object", lambda: self)
        setattr(view, "action", "download")
        try:
            view.check_permissions(drequest)
        except APIException as e:
            raise PermissionError(e)

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = (
            ("download_rbaccontentguard", "Can Download Content"),
            ("manage_roles_rbaccontentguard", "Can manage role assignments on RBAC content guard"),
        )


def _gen_secret():
    return os.urandom(32)


class ContentRedirectContentGuard(ContentGuard, AutoAddObjPermsMixin):
    """
    Content guard to allow preauthenticated redirects to the content app.
    """

    TYPE = "content_redirect"

    EXPIRETIME = timedelta(hours=1)

    shared_secret = models.BinaryField(max_length=32, default=_gen_secret)

    def permit(self, request):
        """
        Permit preauthenticated redirects from pulp-api.
        """
        try:
            expires = request.query["expires"]
            if int(timezone.now().timestamp()) > int(expires):
                raise PermissionError("Authentication expired")
            signed_url = request.url
            validate_token = request.query["validate_token"]
            hex_salt, hex_digest = validate_token.split(":", 1)
            salt = bytes.fromhex(hex_salt)
            digest = bytes.fromhex(hex_digest)
            url = re.sub(r"\&validate_token=.*$", "", str(signed_url))
            if not digest == self._get_digest(salt, url):
                raise PermissionError("Access not authenticated")
        except (KeyError, ValueError):
            raise PermissionError("Access not authenticated")

    def preauthenticate_url(self, url, salt=None):
        """
        Add validate_token to urls query string.
        """
        if not salt:
            salt = _gen_secret()
        hex_salt = salt.hex()
        expiretime = int((timezone.now() + self.EXPIRETIME).timestamp())
        if "?" in url:
            separator = "&"
        else:
            separator = "?"
        url_to_sign = url + separator + f"expires={expiretime}"
        digest = self._get_digest(salt, url_to_sign).hex()
        return url_to_sign + f"&validate_token={hex_salt}:{digest}"

    def _get_digest(self, salt, url):
        url_parts = urlparse(url_normalize(url))
        hasher = hashlib.sha256()
        hasher.update(salt)
        hasher.update(url_parts.path.encode())
        hasher.update(b"?")
        hasher.update(url_parts.query.encode())
        hasher.update(self.shared_secret)
        return hasher.digest()

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = (
            (
                "manage_roles_contentredirectcontentguard",
                "Can manage role assignments on Redirect content guard",
            ),
        )


class BaseDistribution(MasterModel):
    """
    A distribution defines how a publication is distributed by the Content App.

    This abstract model can be used by plugin writers to create concrete distributions that are
    stored in separate tables from the Distributions provided by pulpcore.

    The `name` must be unique.

    The ``base_path`` must have no overlapping components. So if a Distribution with ``base_path``
    of ``a/path/foo`` existed, you could not make a second Distribution with a ``base_path`` of
    ``a/path`` or ``a`` because both are subpaths of ``a/path/foo``.

    Note:
        This class is no longer supported and cannot be removed from Pulp 3 due to possible
        problems with old migrations for plugins. Until the migrations are squashed, this class
        should be preserved.

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

    def __init__(self, *args, **kwargs):
        raise Exception(
            "BaseDistribution is no longer supported. "
            "Please use pulpcore.plugin.models.Distribution instead."
        )


class Distribution(MasterModel):
    """
    A Distribution defines how the Content App distributes a publication or repository_version.

    This master model can be used by plugin writers to create detail Distribution objects.

    The ``name`` must be unique.

    The ``base_path`` must have no overlapping components. So if a Distribution with ``base_path``
    of ``a/path/foo`` existed, you could not make a second Distribution with a ``base_path`` of
    ``a/path`` or ``a`` because both are subpaths of ``a/path/foo``.

    Subclasses are expected to use either the ``publication`` or ``repository_version`` field, but
    not both. The content app that serves content is not prepared to serve content both ways at the
    same time.

    Fields:
        name (models.TextField): The name of the distribution. Examples: "rawhide" and "stable".
        pulp_labels (HStoreField): Dictionary of string values.
        base_path (models.TextField): The base (relative) path component of the published url.
        hidden (models.BooleanField): Whether this distribution should be hidden in the content app.

    Relations:
        content_guard (models.ForeignKey): An optional content-guard.
        publication (models.ForeignKey): Publication to be served.
        remote (models.ForeignKey): A remote that the content app can use to find content not
            yet stored in Pulp.
        repository (models.ForeignKey): The latest RepositoryVersion for this Repository will be
            served.
        repository_version (models.ForeignKey): RepositoryVersion to be served.
        pulp_domain (models.ForeignKey): The domain the Distribution is a part of.
    """

    # If distribution serves publications, set by subclasses for proper handling in content app
    SERVE_FROM_PUBLICATION = False

    name = models.TextField(db_index=True)
    pulp_labels = HStoreField(default=dict)
    base_path = models.TextField()
    pulp_domain = models.ForeignKey("Domain", default=get_domain_pk, on_delete=models.PROTECT)
    hidden = models.BooleanField(default=False, null=True)

    content_guard = models.ForeignKey(ContentGuard, null=True, on_delete=models.SET_NULL)
    publication = models.ForeignKey(Publication, null=True, on_delete=models.SET_NULL)
    remote = models.ForeignKey(Remote, null=True, on_delete=models.SET_NULL)
    repository = models.ForeignKey(
        Repository, null=True, on_delete=models.SET_NULL, related_name="distributions"
    )
    repository_version = models.ForeignKey(RepositoryVersion, null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = (("name", "pulp_domain"), ("base_path", "pulp_domain"))

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

    def content_headers_for(self, path):
        """
        Opportunity for Distribution to specify response-headers for a specific path

        Args:
            path (str): The path being requested
        Returns:
            Empty dictionary, or a dictionary with HTTP Response header/value pairs.
        """
        return {}

    @hook(BEFORE_DELETE)
    @hook(
        AFTER_UPDATE,
        when_any=[
            "base_path",
            "content_guard",
            "publication",
            "remote",
            "repository",
            "repository_version",
        ],
        has_changed=True,
    )
    def invalidate_cache(self):
        """Invalidates the cache if enabled."""
        if settings.CACHE_ENABLED:
            Cache().delete(base_key=cache_key(self.base_path))
            # Can also preload cache here possibly


class ArtifactDistribution(Distribution):
    """Serve artifacts by their uuid."""

    TYPE = "artifact"

    @hook("before_save")
    def ensure_singleton(self):
        cls = self.__class__
        if cls.objects.exists():
            raise RuntimeError(f"This system already has a {cls.__name__}")

    def artifact_url(self, artifact):
        origin = settings.CONTENT_ORIGIN.strip("/")
        prefix = settings.CONTENT_PATH_PREFIX.strip("/")
        base_path = self.base_path.strip("/")
        if settings.DOMAIN_ENABLED:
            base_path = urljoin(artifact.pulp_domain.name + "/", base_path)

        plain_url = urljoin(
            urljoin(urljoin(origin, prefix + "/"), base_path + "/"), str(artifact.pk)
        )
        return self.content_guard.cast().preauthenticate_url(plain_url)

    def content_handler(self, path):
        """Serve an artifact or return 404."""
        uuid = path.rstrip("/")
        if re.match(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uuid):
            artifact = Artifact.objects.filter(pk=uuid).select_related("pulp_domain").first()
            if artifact:
                return ArtifactResponse(artifact)
        raise HTTPNotFound()

    class Meta:
        default_related_name = "%(app_label)s_%(model_name)s"
        permissions = [
            ("manage_roles_artifactdistribution", "Can manage roles on artifact distributions"),
        ]
