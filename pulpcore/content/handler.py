import logging
import mimetypes
import os
import re
from gettext import gettext as _

from aiohttp.client_exceptions import ClientResponseError
from aiohttp.web import FileResponse, StreamResponse, HTTPOk
from aiohttp.web_exceptions import HTTPForbidden, HTTPFound, HTTPNotFound

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
    IntegrityError,
    transaction,
)
from pulpcore.app.models import (  # noqa: E402: module level not at top of file
    Artifact,
    BaseDistribution,
    ContentArtifact,
    Remote,
    RemoteArtifact,
)

from jinja2 import Template  # noqa: E402: module level not at top of file

log = logging.getLogger(__name__)


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

        if self.distribution_model is None:
            distributions = BaseDistribution.objects.only("base_path").all()
        else:
            distributions = self.distribution_model.objects.only("base_path").all()
        directory_list = ["{}/".format(d.base_path) for d in distributions]
        return HTTPOk(headers={"Content-Type": "text/html"}, body=self.render_html(directory_list))

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
            detail of BaseDistribution: The matched distribution.

        Raises:
            PathNotResolved: when not matched.
        """
        base_paths = cls._base_paths(path)
        try:
            if cls.distribution_model is None:
                model_class = BaseDistribution
                return BaseDistribution.objects.get(base_path__in=base_paths).cast()
            else:
                model_class = cls.distribution_model
                return cls.distribution_model.objects.get(base_path__in=base_paths)
        except ObjectDoesNotExist:
            log.debug(
                _("{model_name} not matched for {path} using: {base_paths}").format(
                    model_name=model_class.__name__, path=path, base_paths=base_paths
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
            distribution (detail of :class:`pulpcore.plugin.models.BaseDistribution`): The matched
                distribution.

        Raises:
            :class:`aiohttp.web_exceptions.HTTPForbidden`: When not permitted.
        """
        guard = distribution.content_guard
        if not guard:
            return
        try:
            guard.cast().permit(request)
        except PermissionError as pe:
            log.debug(
                _('Path: %(p)s not permitted by guard: "%(g)s" reason: %(r)s'),
                {"p": request.path, "g": guard.name, "r": str(pe)},
            )
            raise HTTPForbidden(reason=str(pe))

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
        if not publication and not repo_version:
            raise Exception("Either a repo_version or publication is required.")
        if publication and repo_version:
            raise Exception("Either a repo_version or publication can be specified.")

        def file_or_directory_name(directory_path, relative_path):
            result = re.match(r"({})([^\/]*)(\/*)".format(directory_path), relative_path)
            return "{}{}".format(result.groups()[1], result.groups()[2])

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

    async def _match_and_stream(self, path, request):
        """
        Match the path and stream results either from the filesystem or by downloading new data.

        After deciding the client can access the distribution at ``path``, this function calls
        :meth:`BaseDistribution.content_handler`. If that function returns a not-None result,
        it is returned to the client.

        Then the publication linked to the Distribution is used to determine what content should
        be served. If ``path`` is a directory entry (i.e. not a file), the directory contents
        are served to the client. This method calls
        :meth:`BaseDistribution.content_handler_list_directory` to acquire any additional entries
        the Distribution's content_handler might serve in that directory. If there is an actifact
        to be served, it is served to the client.

        If there's no publication, the above paragraph is applied to the lastest repository linked
        to the matched Distribution.

        Finally, when nothing is served to client yet, we check if there is a remote for the
        Distribution. If so, the artifact is pulled from the remote and streamed to the client.

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
        distro = self._match_distribution(path)
        self._permit(request, distro)

        rel_path = path.lstrip("/")
        rel_path = rel_path[len(distro.base_path) :]
        rel_path = rel_path.lstrip("/")

        content_handler_result = distro.content_handler(rel_path)
        if content_handler_result is not None:
            return content_handler_result

        headers = self.response_headers(rel_path)

        publication = getattr(distro, "publication", None)

        if publication:
            if rel_path == "" or rel_path[-1] == "/":
                try:
                    index_path = "{}index.html".format(rel_path)
                    publication.published_artifact.get(relative_path=index_path)
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
                pa = publication.published_artifact.get(relative_path=rel_path)
                ca = pa.content_artifact
            except ObjectDoesNotExist:
                pass
            else:
                if ca.artifact:
                    return self._serve_content_artifact(ca, headers)
                else:
                    return await self._stream_content_artifact(
                        request, StreamResponse(headers=headers), ca
                    )

            # pass-through
            if publication.pass_through:
                try:
                    ca = ContentArtifact.objects.get(
                        content__in=publication.repository_version.content, relative_path=rel_path
                    )
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
                        return self._serve_content_artifact(ca, headers)
                    else:
                        return await self._stream_content_artifact(
                            request, StreamResponse(headers=headers), ca
                        )

        repo_version = getattr(distro, "repository_version", None)
        repository = getattr(distro, "repository", None)

        if repository or repo_version:
            if repository:
                repo_version = distro.repository.latest_version()

            if rel_path == "" or rel_path[-1] == "/":
                try:
                    index_path = "{}index.html".format(rel_path)
                    ContentArtifact.objects.get(
                        content__in=repo_version.content, relative_path=index_path
                    )
                    rel_path = index_path
                except ObjectDoesNotExist:
                    dir_list = await self.list_directory(repo_version, None, rel_path)
                    dir_list.update(distro.content_handler_list_directory(rel_path))
                    return HTTPOk(
                        headers={"Content-Type": "text/html"}, body=self.render_html(dir_list)
                    )

            try:
                ca = ContentArtifact.objects.get(
                    content__in=repo_version.content, relative_path=rel_path
                )
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
                    return self._serve_content_artifact(ca, headers)
                else:
                    return await self._stream_content_artifact(
                        request, StreamResponse(headers=headers), ca
                    )

        if distro.remote:
            remote = distro.remote.cast()
            try:
                url = remote.get_remote_artifact_url(rel_path)
                ra = RemoteArtifact.objects.get(remote=remote, url=url)
                ca = ra.content_artifact
                if ca.artifact:
                    return self._serve_content_artifact(ca, headers)
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
        for remote_artifact in content_artifact.remoteartifact_set.all():
            try:
                response = await self._stream_remote_artifact(request, response, remote_artifact)
                return response

            except ClientResponseError:
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
                artifact = Artifact.objects.get(artifact.q())
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

    def _serve_content_artifact(self, content_artifact, headers):
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
        if settings.DEFAULT_FILE_STORAGE == "pulpcore.app.models.storage.FileSystem":
            filename = content_artifact.artifact.file.name
            return FileResponse(os.path.join(settings.MEDIA_ROOT, filename), headers=headers)
        elif (
            settings.DEFAULT_FILE_STORAGE == "storages.backends.s3boto3.S3Boto3Storage"
            or settings.DEFAULT_FILE_STORAGE == "storages.backends.azure_storage.AzureStorage"
        ):
            artifact_file = content_artifact.artifact.file
            content_disposition = f"attachment;filename={content_artifact.relative_path}"
            parameters = {"ResponseContentDisposition": content_disposition}
            url = artifact_file.storage.url(artifact_file.name, parameters=parameters)
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
        remote = remote_artifact.remote.cast()

        async def handle_headers(headers):
            for name, value in headers.items():
                if name.lower() in self.hop_by_hop_headers:
                    continue
                response.headers[name] = value
            await response.prepare(request)

        async def handle_data(data):
            await response.write(data)
            if remote.policy != Remote.STREAMED:
                await original_handle_data(data)

        async def finalize():
            if remote.policy != Remote.STREAMED:
                await original_finalize()

        downloader = remote.get_downloader(
            remote_artifact=remote_artifact, headers_ready_callback=handle_headers
        )
        original_handle_data = downloader.handle_data
        downloader.handle_data = handle_data
        original_finalize = downloader.finalize
        downloader.finalize = finalize
        download_result = await downloader.run()

        if remote.policy != Remote.STREAMED:
            self._save_artifact(download_result, remote_artifact)
        await response.write_eof()

        if response.status == 404:
            raise HTTPNotFound()
        return response
