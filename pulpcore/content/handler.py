import asyncio
import logging
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor
from gettext import gettext as _

from aiohttp.client_exceptions import ClientResponseError
from aiohttp.web import FileResponse, StreamResponse, HTTPOk
from aiohttp.web_exceptions import HTTPForbidden, HTTPFound, HTTPNotFound
from yarl import URL

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")
django.setup()

from django.conf import settings  # noqa: E402: module level not at top of file
from django.core.exceptions import (  # noqa: E402: module level not at top of file
    MultipleObjectsReturned,
    ObjectDoesNotExist,
)
from django.db import (  # noqa: E402: module level not at top of file
    connection,
    DatabaseError,
    IntegrityError,
    transaction,
)
from pulpcore.app.models import (  # noqa: E402: module level not at top of file
    Artifact,
    ContentArtifact,
    Distribution,
    Publication,
    Remote,
    RemoteArtifact,
)
from pulpcore.exceptions import UnsupportedDigestValidationError  # noqa: E402

from jinja2 import Template  # noqa: E402: module level not at top of file
from pulpcore.cache import ContentCache  # noqa: E402

log = logging.getLogger(__name__)


loop = asyncio.get_event_loop()
# Django ORM is blocking, as are most of our file operations. This means that the
# standard single-threaded async executor cannot help us. We need to create a separate,
# thread-based executor to pass our heavy blocking IO work to.
io_pool_exc = ThreadPoolExecutor(max_workers=2)
loop.set_default_executor(io_pool_exc)


class PathNotResolved(HTTPNotFound):
    """
    The path could not be resolved to a published file.

    This could be caused by either the distribution, the publication,
    or the published file could not be found.
    """

    def __init__(self, path, *args, **kwargs):
        """Initialize the Exception."""
        self.path = path
        super().__init__(*args, **kwargs)


class ArtifactNotFound(Exception):
    """
    The artifact associated with a published-artifact does not exist.
    """

    pass


class Handler:
    """
    A default Handler for the Content App that also can be subclassed to create custom handlers.

    This Handler will perform the following:

    1. Match the request against a Distribution

    2. Call the certguard check if a certguard exists for the matched Distribution.

    3. If the Distribution has a `publication` serve that Publication's `PublishedArtifacts`,
       `PublishedMetadata` by the remaining `relative path`. If still unserved and if `pass_through`
       is set, the associated `repository_version` will have its `ContentArtifacts` served by
       `relative_path` also. This will serve the associated `Artifact`.

    4. If still unmatched, and the Distribution has a `repository` attribute set, find it's latest
       `repository_version`. If the Distribution has a `repository_version` attribute set, use that.
       For this `repository_version`, find matching `ContentArtifact` objects by `relative_path` and
       serve them. If there is an associated `Artifact` return it.

    5. If the Distribution has a `remote`, find an associated `RemoteArtifact` that matches by
       `relative_path`. Fetch and stream the corresponding `RemoteArtifact` to the client,
       optionally saving the `Artifact` depending on the `policy` attribute.

    """

    hop_by_hop_headers = [
        "connection",
        "keep-alive",
        "public",
        "proxy-authenticate",
        "transfer-encoding",
        "upgrade",
    ]

    distribution_model = None

    @staticmethod
    def _reset_db_connection():
        """
        Reset database connection if it's unusable or obselete to avoid "connection already closed".
        """
        connection.close_if_unusable_or_obsolete()

    async def list_distributions(self, request):
        """
        The handler for an HTML listing all distributions

        Args:
            request (:class:`aiohttp.web.request`): The request from the client.

        Returns:
            :class:`aiohttp.web.HTTPOk`: The response back to the client.
        """
        self._reset_db_connection()

        def get_base_paths_blocking():
            if self.distribution_model is None:
                base_paths = list(Distribution.objects.values_list("base_path", flat=True))
            else:
                base_paths = list(
                    self.distribution_model.objects.values_list("base_path", flat=True)
                )
            return base_paths

        base_paths = await loop.run_in_executor(None, get_base_paths_blocking)
        directory_list = ["{}/".format(path) for path in base_paths]
        return HTTPOk(headers={"Content-Type": "text/html"}, body=self.render_html(directory_list))

    @classmethod
    async def find_base_path_cached(cls, request, cached):
        """
        Finds the base-path to use for the base-key in the cache

        Args:
            request (:class:`aiohttp.web.request`): The request from the client.
            cached (:class:`CacheAiohttp`): The Pulp cache

        Returns:
            str: The base-path associated with this request
        """
        path = request.match_info["path"]
        base_paths = cls._base_paths(path)
        multiplied_base_paths = []
        for i, base_path in enumerate(base_paths):
            copied_by_index_base_path = [base_path for _ in range(i + 1)]
            multiplied_base_paths.extend(copied_by_index_base_path)
        index_p1 = await cached.exists(base_key=multiplied_base_paths)
        if index_p1:
            return base_paths[index_p1 - 1]
        else:
            distro = await loop.run_in_executor(None, cls._match_distribution, path)
            return distro.base_path

    @classmethod
    async def auth_cached(cls, request, cached, base_key):
        """
        Authentication check for the cached stream_content handler

        Args:
            request (:class:`aiohttp.web.request`): The request from the client.
            cached (:class:`CacheAiohttp`): The Pulp cache
            base_key (str): The base_key associated with this response
        """
        guard_key = "DISTRO#GUARD#PRESENT"
        present = await cached.get(guard_key, base_key=base_key)
        if present == b"True" or present is None:
            path = request.match_info["path"]
            distro = await loop.run_in_executor(None, cls._match_distribution, path)
            try:
                guard = await loop.run_in_executor(None, cls._permit, request, distro)
            except HTTPForbidden:
                guard = True
                raise
            finally:
                if not present:
                    await cached.set(guard_key, str(guard), base_key=base_key)

    @ContentCache(
        base_key=lambda req, cac: Handler.find_base_path_cached(req, cac),
        auth=lambda req, cac, bk: Handler.auth_cached(req, cac, bk),
    )
    async def stream_content(self, request):
        """
        The request handler for the Content app.

        Args:
            request (:class:`aiohttp.web.request`): The request from the client.

        Returns:
            :class:`aiohttp.web.StreamResponse` or :class:`aiohttp.web.FileResponse`: The response
                back to the client.
        """
        self._reset_db_connection()

        path = request.match_info["path"]
        return await self._match_and_stream(path, request)

    @staticmethod
    def _base_paths(path):
        """
        Get a list of base paths used to match a distribution.

        Args:
            path (str): The path component of the URL.

        Returns:
            list: Of base paths.

        """
        tree = []
        while True:
            base = os.path.split(path)[0]
            if not base.lstrip("/"):
                break
            tree.append(base)
            path = base
        return tree

    @classmethod
    def _match_distribution(cls, path):
        """
        Match a distribution using a list of base paths and return its detail object.

        Args:
            path (str): The path component of the URL.

        Returns:
            The detail object of the matched distribution.

        Raises:
            PathNotResolved: when not matched.
        """
        base_paths = cls._base_paths(path)
        if cls.distribution_model is None:
            try:
                return (
                    Distribution.objects.select_related(
                        "repository", "repository_version", "publication", "remote"
                    )
                    .get(base_path__in=base_paths)
                    .cast()
                )
            except ObjectDoesNotExist:
                log.debug(
                    _("Distribution not matched for {path} using: {base_paths}").format(
                        path=path, base_paths=base_paths
                    )
                )
        else:
            try:
                return cls.distribution_model.objects.select_related(
                    "repository", "repository_version", "publication", "remote"
                ).get(base_path__in=base_paths)
            except ObjectDoesNotExist:
                log.debug(
                    _("Distribution not matched for {path} using: {base_paths}").format(
                        path=path, base_paths=base_paths
                    )
                )
        raise PathNotResolved(path)

    @staticmethod
    def _permit(request, distribution):
        """
        Permit the request.

        Authorization is delegated to the optional content-guard associated with the distribution.

        Args:
            request (:class:`aiohttp.web.Request`): A request for a published file.
            distribution (detail of :class:`pulpcore.plugin.models.Distribution`): The matched
                distribution.

        Raises:
            :class:`aiohttp.web_exceptions.HTTPForbidden`: When not permitted.
        """
        guard = distribution.content_guard
        if not guard:
            return False
        try:
            guard.cast().permit(request)
        except PermissionError as pe:
            log.debug(
                _('Path: %(p)s not permitted by guard: "%(g)s" reason: %(r)s'),
                {"p": request.path, "g": guard.name, "r": str(pe)},
            )
            raise HTTPForbidden(reason=str(pe))
        return True

    @staticmethod
    def response_headers(path):
        """
        Get the Content-Type and Encoding-Type headers for the requested `path`.

        Args:
            path (str): The relative path that was requested.

        Returns:
            headers (dict): A dictionary of response headers.
        """
        content_type, encoding = mimetypes.guess_type(path)
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    @staticmethod
    def render_html(directory_list):
        """
        Render a list of strings as an HTML list of links.

        Args:
            directory_list (iterable): an iterable of strings representing file and directory names

        Returns:
            String representing HTML of the directory listing.
        """
        template = Template(
            """
        <!DOCTYPE html>
        <html>
            <body>
                <ul>
                {% for name in dir_list %}
                    <li><a href="{{ name|e }}">{{ name|e }}</a></li>
                {% endfor %}
                </ul>
            </body>
        </html>
        """
        )
        return template.render(dir_list=sorted(directory_list))

    async def list_directory(self, repo_version, publication, path):
        """
        Generate a set with directory listing of the path.

        This method expects either a repo_version or a publication in addition to a path. This
        method generates a set of strings representing the list of a path inside the repository
        version or publication.

        Args:
            repo_version (:class:`~pulpcore.app.models.RepositoryVersion`): The repository version
            publication (:class:`~pulpcore.app.models.Publication`): Publication
            path (str): relative path inside the repo version of publication.

        Returns:
            Set of strings representing the files and directories in the directory listing.
        """

        def file_or_directory_name(directory_path, relative_path):
            result = re.match(r"({})([^\/]*)(\/*)".format(directory_path), relative_path)
            return "{}{}".format(result.groups()[1], result.groups()[2])

        def list_directory_blocking():
            if not publication and not repo_version:
                raise Exception("Either a repo_version or publication is required.")
            if publication and repo_version:
                raise Exception("Either a repo_version or publication can be specified.")

            directory_list = set()

            if publication:
                pas = publication.published_artifact.filter(relative_path__startswith=path)
                for pa in pas:
                    directory_list.add(file_or_directory_name(path, pa.relative_path))

                if publication.pass_through:
                    cas = ContentArtifact.objects.filter(
                        content__in=publication.repository_version.content,
                        relative_path__startswith=path,
                    )
                    for ca in cas:
                        directory_list.add(file_or_directory_name(path, ca.relative_path))

            if repo_version:
                cas = ContentArtifact.objects.filter(
                    content__in=repo_version.content, relative_path__startswith=path
                )
                for ca in cas:
                    directory_list.add(file_or_directory_name(path, ca.relative_path))

            if directory_list:
                return directory_list
            else:
                raise PathNotResolved(path)

        return await loop.run_in_executor(None, list_directory_blocking)

    async def _match_and_stream(self, path, request):
        """
        Match the path and stream results either from the filesystem or by downloading new data.

        After deciding the client can access the distribution at ``path``, this function calls
        :meth:`Distribution.content_handler`. If that function returns a not-None result, it is
        returned to the client.

        Then the publication linked to the Distribution is used to determine what content should
        be served. If ``path`` is a directory entry (i.e. not a file), the directory contents
        are served to the client. This method calls
        :meth:`Distribution.content_handler_list_directory` to acquire any additional entries the
        Distribution's content_handler might serve in that directory. If there is an Artifact to be
        served, it is served to the client.

        If there's no publication, the above paragraph is applied to the latest repository linked
        to the matched Distribution.

        Finally, when nothing is served to client yet, we check if there is a remote for the
        Distribution. If so, the Artifact is pulled from the remote and streamed to the client.

        Args:
            path (str): The path component of the URL.
            request(:class:`~aiohttp.web.Request`): The request to prepare a response for.

        Raises:
            PathNotResolved: The path could not be matched to a published file.
            PermissionError: When not permitted.

        Returns:
            :class:`aiohttp.web.StreamResponse` or :class:`aiohttp.web.FileResponse`: The response
                streamed back to the client.
        """

        def match_distribution_blocking():
            return self._match_distribution(path)

        distro = await loop.run_in_executor(None, match_distribution_blocking)

        def check_permit_blocking():
            self._permit(request, distro)

        await loop.run_in_executor(None, check_permit_blocking)

        rel_path = path.lstrip("/")
        rel_path = rel_path[len(distro.base_path) :]
        rel_path = rel_path.lstrip("/")

        content_handler_result = distro.content_handler(rel_path)
        if content_handler_result is not None:
            return content_handler_result

        headers = self.response_headers(rel_path)

        repository = distro.repository
        publication = distro.publication
        repo_version = distro.repository_version

        if repository:

            def get_latest_publication_or_version_blocking():
                nonlocal repo_version
                nonlocal publication

                # Search for publication serving the closest latest version
                if not publication:
                    try:
                        versions = repository.versions.all()
                        publications = Publication.objects.filter(
                            repository_version__in=versions, complete=True
                        )
                        publication = publications.select_related("repository_version").latest(
                            "repository_version", "pulp_created"
                        )
                        repo_version = publication.repository_version
                    except ObjectDoesNotExist:
                        pass

                if not repo_version:
                    repo_version = repository.latest_version()

            await loop.run_in_executor(None, get_latest_publication_or_version_blocking)

        if publication:
            if rel_path == "" or rel_path[-1] == "/":
                try:
                    index_path = "{}index.html".format(rel_path)

                    def get_published_artifact_blocking():
                        publication.published_artifact.get(relative_path=index_path)

                    await loop.run_in_executor(None, get_published_artifact_blocking)

                    rel_path = index_path
                    headers = self.response_headers(rel_path)
                except ObjectDoesNotExist:
                    dir_list = await self.list_directory(None, publication, rel_path)
                    dir_list.update(distro.content_handler_list_directory(rel_path))
                    return HTTPOk(
                        headers={"Content-Type": "text/html"}, body=self.render_html(dir_list)
                    )

            # published artifact
            try:

                def get_contentartifact_blocking():
                    return (
                        publication.published_artifact.select_related(
                            "content_artifact",
                            "content_artifact__artifact",
                        )
                        .get(relative_path=rel_path)
                        .content_artifact
                    )

                ca = await loop.run_in_executor(None, get_contentartifact_blocking)
            except ObjectDoesNotExist:
                pass
            else:
                if ca.artifact:
                    return await self._serve_content_artifact(ca, headers)
                else:
                    return await self._stream_content_artifact(
                        request, StreamResponse(headers=headers), ca
                    )

            # pass-through
            if publication.pass_through:
                try:

                    def get_contentartifact_blocking():
                        ca = ContentArtifact.objects.select_related("artifact").get(
                            content__in=publication.repository_version.content,
                            relative_path=rel_path,
                        )
                        return ca

                    ca = await loop.run_in_executor(None, get_contentartifact_blocking)
                except MultipleObjectsReturned:
                    log.error(
                        _("Multiple (pass-through) matches for {b}/{p}"),
                        {"b": distro.base_path, "p": rel_path},
                    )
                    raise
                except ObjectDoesNotExist:
                    pass
                else:
                    if ca.artifact:
                        return await self._serve_content_artifact(ca, headers)
                    else:
                        return await self._stream_content_artifact(
                            request, StreamResponse(headers=headers), ca
                        )

        if repo_version:
            if rel_path == "" or rel_path[-1] == "/":
                index_path = "{}index.html".format(rel_path)

                def contentartifact_exists_blocking():
                    return ContentArtifact.objects.filter(
                        content__in=repo_version.content, relative_path=index_path
                    ).exists()

                contentartifact_exists = await loop.run_in_executor(
                    None, contentartifact_exists_blocking
                )
                if contentartifact_exists:
                    rel_path = index_path
                else:
                    dir_list = await self.list_directory(repo_version, None, rel_path)
                    dir_list.update(distro.content_handler_list_directory(rel_path))
                    return HTTPOk(
                        headers={"Content-Type": "text/html"}, body=self.render_html(dir_list)
                    )

            try:

                def get_contentartifact_blocking():
                    ca = ContentArtifact.objects.select_related("artifact").get(
                        content__in=repo_version.content, relative_path=rel_path
                    )
                    return ca

                ca = await loop.run_in_executor(None, get_contentartifact_blocking)
            except MultipleObjectsReturned:
                log.error(
                    _("Multiple (pass-through) matches for {b}/{p}"),
                    {"b": distro.base_path, "p": rel_path},
                )
                raise
            except ObjectDoesNotExist:
                pass
            else:
                if ca.artifact:
                    return await self._serve_content_artifact(ca, headers)
                else:
                    return await self._stream_content_artifact(
                        request, StreamResponse(headers=headers), ca
                    )

        if distro.remote:

            def cast_remote_blocking():
                return distro.remote.cast()

            remote = await loop.run_in_executor(None, cast_remote_blocking)

            try:
                url = remote.get_remote_artifact_url(rel_path)

                def get_remote_artifact_blocking():
                    ra = RemoteArtifact.objects.select_related(
                        "content_artifact",
                        "content_artifact__artifact",
                        "remote",
                    ).get(remote=remote, url=url)
                    return ra

                ra = await loop.run_in_executor(None, get_remote_artifact_blocking)
                ca = ra.content_artifact
                if ca.artifact:
                    return await self._serve_content_artifact(ca, headers)
                else:
                    return await self._stream_content_artifact(
                        request, StreamResponse(headers=headers), ca
                    )
            except ObjectDoesNotExist:
                ca = ContentArtifact(relative_path=rel_path)
                ra = RemoteArtifact(remote=remote, url=url, content_artifact=ca)
                return await self._stream_remote_artifact(
                    request, StreamResponse(headers=headers), ra
                )

        raise PathNotResolved(path)

    async def _stream_content_artifact(self, request, response, content_artifact):
        """
        Stream and optionally save a ContentArtifact by requesting it using the associated remote.

        If a fatal download failure occurs while downloading and there are additional
        :class:`~pulpcore.plugin.models.RemoteArtifact` objects associated with the
        :class:`~pulpcore.plugin.models.ContentArtifact` they will also be tried. If all
        :class:`~pulpcore.plugin.models.RemoteArtifact` downloads raise exceptions, an HTTP 502
        error is returned to the client.

        Args:
            request(:class:`~aiohttp.web.Request`): The request to prepare a response for.
            response (:class:`~aiohttp.web.StreamResponse`): The response to stream data to.
            content_artifact (:class:`~pulpcore.plugin.models.ContentArtifact`): The ContentArtifact
                to fetch and then stream back to the client

        Raises:
            :class:`~aiohttp.web.HTTPNotFound` when no
                :class:`~pulpcore.plugin.models.RemoteArtifact` objects associated with the
                :class:`~pulpcore.plugin.models.ContentArtifact` returned the binary data needed for
                the client.
        """

        def get_remote_artifacts_blocking():
            return list(content_artifact.remoteartifact_set.all())

        remote_artifacts = await loop.run_in_executor(None, get_remote_artifacts_blocking)
        for remote_artifact in remote_artifacts:
            try:
                response = await self._stream_remote_artifact(request, response, remote_artifact)
                return response

            except (ClientResponseError, UnsupportedDigestValidationError) as e:
                log.warning(
                    _("Could not download remote artifact at '{}': {}").format(
                        remote_artifact.url, str(e)
                    )
                )
                continue

        raise HTTPNotFound()

    def _save_artifact(self, download_result, remote_artifact):
        """
        Create/Get an Artifact and associate it to a RemoteArtifact and/or ContentArtifact.

        Create (or get if already existing) an :class:`~pulpcore.plugin.models.Artifact`
        based on the `download_result` and associate it to the `content_artifact` of the given
        `remote_artifact`. Both the created artifact and the updated content_artifact are saved to
        the DB.  The `remote_artifact` is also saved for the pull-through caching use case.

        Plugin-writers may overide this method if their content module requires
        additional/different steps for saving.

        Args:
            download_result (:class:`~pulpcore.plugin.download.DownloadResult`: The
                DownloadResult for the downloaded artifact.

            remote_artifact (:class:`~pulpcore.plugin.models.RemoteArtifact`): The
                RemoteArtifact to associate the Artifact with.

        Returns:
            The associated :class:`~pulpcore.plugin.models.Artifact`.
        """
        content_artifact = remote_artifact.content_artifact
        remote = remote_artifact.remote
        artifact = Artifact(**download_result.artifact_attributes, file=download_result.path)
        with transaction.atomic():
            try:
                with transaction.atomic():
                    artifact.save()
            except IntegrityError:
                try:
                    artifact = Artifact.objects.get(artifact.q())
                    artifact.touch()
                except (Artifact.DoesNotExist, DatabaseError):
                    # it's possible that orphan cleanup deleted the artifact
                    # so fall back to creating a new artifact again
                    artifact = Artifact(
                        **download_result.artifact_attributes, file=download_result.path
                    )
                    artifact.save()
            update_content_artifact = True
            if content_artifact._state.adding:
                # This is the first time pull-through content was requested.
                rel_path = content_artifact.relative_path
                c_type = remote.get_remote_artifact_content_type(rel_path)
                content = c_type.init_from_artifact_and_relative_path(artifact, rel_path)
                try:
                    with transaction.atomic():
                        content.save()
                        content_artifact.content = content
                        content_artifact.save()
                except IntegrityError:
                    # There is already content for this Artifact
                    content = c_type.objects.get(content.q())
                    artifacts = content._artifacts
                    if artifact.sha256 != artifacts[0].sha256:
                        raise RuntimeError(
                            "The Artifact downloaded during pull-through does not "
                            "match the Artifact already stored for the same "
                            "content."
                        )
                    content_artifact = ContentArtifact.objects.get(content=content)
                    update_content_artifact = False
                try:
                    with transaction.atomic():
                        remote_artifact.content_artifact = content_artifact
                        remote_artifact.save()
                except IntegrityError:
                    # Remote artifact must have already gotten saved during a parallel request
                    log.info("RemoteArtifact already exists.")
            if update_content_artifact:
                content_artifact.artifact = artifact
                content_artifact.save()
        return artifact

    async def _serve_content_artifact(self, content_artifact, headers):
        """
        Handle response for a Content Artifact with the file present.

        Depending on where the file storage (e.g. filesystem, S3, etc) this could be responding with
        the file (filesystem) or a redirect (S3).

        Args:
            content_artifact (:class:`pulpcore.app.models.ContentArtifact`): The Content Artifact to
                respond with.
            headers (dict): A dictionary of response headers.

        Raises:
            :class:`aiohttp.web_exceptions.HTTPFound`: When we need to redirect to the file
            NotImplementedError: If file is stored in a file storage we can't handle

        Returns:
            The :class:`aiohttp.web.FileResponse` for the file.
        """
        artifact_file = content_artifact.artifact.file
        artifact_name = artifact_file.name

        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            return FileResponse(os.path.join(settings.MEDIA_ROOT, artifact_name), headers=headers)
        elif settings.DEFAULT_FILE_STORAGE == "storages.backends.s3boto3.S3Boto3Storage":
            content_disposition = f"attachment;filename={content_artifact.relative_path}"
            parameters = {"ResponseContentDisposition": content_disposition}
            url = URL(
                artifact_file.storage.url(artifact_file.name, parameters=parameters), encoded=True
            )
            raise HTTPFound(url)
        elif settings.DEFAULT_FILE_STORAGE == "storages.backends.azure_storage.AzureStorage":
            url = URL(artifact_file.storage.url(artifact_name), encoded=True)
            raise HTTPFound(url)
        else:
            raise NotImplementedError()

    async def _stream_remote_artifact(self, request, response, remote_artifact):
        """
        Stream and save a RemoteArtifact.

        Args:
            request(:class:`~aiohttp.web.Request`): The request to prepare a response for.
            response (:class:`~aiohttp.web.StreamResponse`): The response to stream data to.
            content_artifact (:class:`~pulpcore.plugin.models.ContentArtifact`): The ContentArtifact
                to fetch and then stream back to the client

        Raises:
            :class:`~aiohttp.web.HTTPNotFound` when no
                :class:`~pulpcore.plugin.models.RemoteArtifact` objects associated with the
                :class:`~pulpcore.plugin.models.ContentArtifact` returned the binary data needed for
                the client.

        """

        def cast_remote_blocking():
            return remote_artifact.remote.cast()

        remote = await loop.run_in_executor(None, cast_remote_blocking)

        range_start, range_stop = request.http_range.start, request.http_range.stop
        if range_start or range_stop:
            response.set_status(206)

        async def handle_response_headers(headers):
            for name, value in headers.items():
                lower_name = name.lower()
                if lower_name in self.hop_by_hop_headers:
                    continue

                if response.status == 206 and lower_name == "content-length":
                    range_bytes = int(value)
                    start = 0 if range_start is None else range_start
                    stop = range_bytes if range_stop is None else range_stop

                    range_bytes = range_bytes - range_start
                    range_bytes = range_bytes - (int(value) - stop)
                    response.headers[name] = str(range_bytes)

                    response.headers["Content-Range"] = "bytes {0}-{1}/{2}".format(
                        start, stop - start + 1, int(value)
                    )
                    continue

                response.headers[name] = value
            await response.prepare(request)

        data_size_handled = 0

        async def handle_data(data):
            nonlocal data_size_handled
            if range_start or range_stop:
                start_byte_pos = 0
                end_byte_pos = len(data)
                if range_start:
                    start_byte_pos = max(0, range_start - data_size_handled)
                if range_stop:
                    end_byte_pos = min(len(data), range_stop - data_size_handled)

                data_for_client = data[start_byte_pos:end_byte_pos]
                await response.write(data_for_client)
                data_size_handled = data_size_handled + len(data)
            else:
                await response.write(data)
            if remote.policy != Remote.STREAMED:
                await original_handle_data(data)

        async def finalize():
            if remote.policy != Remote.STREAMED:
                await original_finalize()

        downloader = remote.get_downloader(
            remote_artifact=remote_artifact, headers_ready_callback=handle_response_headers
        )
        original_handle_data = downloader.handle_data
        downloader.handle_data = handle_data
        original_finalize = downloader.finalize
        downloader.finalize = finalize
        download_result = await downloader.run()

        if remote.policy != Remote.STREAMED:

            def save_artifact_blocking():
                self._save_artifact(download_result, remote_artifact)

            await asyncio.shield(loop.run_in_executor(None, save_artifact_blocking))
        await response.write_eof()

        if response.status == 404:
            raise HTTPNotFound()
        return response
