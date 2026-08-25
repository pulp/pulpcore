import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from aiohttp.web_exceptions import (
    HTTPFound,
    HTTPMovedPermanently,
    HTTPNotModified,
)
from asgiref.sync import sync_to_async
from django.db import IntegrityError
from django.test import override_settings
from django.utils.http import http_date
from django_guid import clear_guid, set_guid

from pulpcore.app.models import AppStatus
from pulpcore.constants import TASK_STATES
from pulpcore.content.handler import CheckpointListings, Handler, PathNotResolved
from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    Distribution,
    Publication,
    Remote,
    RemoteArtifact,
    Repository,
    RepositoryVersion,
)


@pytest.fixture
def download_result_mock(tmp_path):
    dr = Mock()
    dr.artifact_attributes = {"size": 0}
    for digest_type in Artifact.DIGEST_FIELDS:
        dr.artifact_attributes[digest_type] = "abc123"
    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text("abc123")
    dr.path = str(tmp_file)
    return dr


@pytest.fixture
def c1(db):
    return Content.objects.create()


@pytest.fixture
def ca1(c1):
    return ContentArtifact.objects.create(artifact=None, content=c1, relative_path="c1")


@pytest.fixture
def ra1(ca1):
    return Mock(content_artifact=ca1)


@pytest.fixture
def c2(db):
    return Content.objects.create()


@pytest.fixture
def ca2(c2):
    return ContentArtifact.objects.create(artifact=None, content=c2, relative_path="c1")


@pytest.fixture
def ra2(ca2):
    return Mock(content_artifact=ca2)


@pytest.fixture
def repo():
    return Repository.objects.create(name=str(uuid.uuid4()))


@pytest.fixture
def repo_version_1(repo):
    return RepositoryVersion.objects.create(repository=repo, number=1)


@pytest.fixture
def repo_version_2(repo):
    return RepositoryVersion.objects.create(repository=repo, number=2)


@pytest.fixture
def repo_version_3(repo):
    return RepositoryVersion.objects.create(repository=repo, number=3)


@pytest.fixture
def checkpoint_distribution(repo):
    return Distribution.objects.create(
        name=str(uuid.uuid4()), base_path=str(uuid.uuid4()), repository=repo, checkpoint=True
    )


@pytest.fixture
def checkpoint_publication_1(repo_version_1):
    publication = Publication.objects.create(repository_version=repo_version_1, checkpoint=True)
    # Avoid creating publications in the future, which would cause a 404
    publication.pulp_created = publication.pulp_created - timedelta(seconds=6)
    publication.save()

    return publication


@pytest.fixture
def noncheckpoint_publication(repo_version_2, checkpoint_publication_1):
    publication = Publication.objects.create(repository_version=repo_version_2, checkpoint=False)
    publication.pulp_created = checkpoint_publication_1.pulp_created + timedelta(seconds=2)
    publication.save()

    return publication


@pytest.fixture
def checkpoint_publication_2(repo_version_3, noncheckpoint_publication):
    publication = Publication.objects.create(repository_version=repo_version_3, checkpoint=True)
    publication.pulp_created = noncheckpoint_publication.pulp_created + timedelta(seconds=2)
    publication.save()

    return publication


def test_save_artifact(c1, ra1, download_result_mock):
    """Artifact needs to be created."""
    handler = Handler()
    content_artifacts = handler._save_artifact(download_result_mock, ra1)
    c1 = Content.objects.get(pk=c1.pk)
    assert content_artifacts is not None
    assert ra1.content_artifact.relative_path in content_artifacts
    artifact = content_artifacts[ra1.content_artifact.relative_path].artifact
    assert c1._artifacts.get().pk == artifact.pk


def test_save_artifact_artifact_already_exists(c2, ra1, ra2, download_result_mock):
    """Artifact turns out to already exist."""
    cch = Handler()
    new_content_artifacts = cch._save_artifact(download_result_mock, ra1)

    existing_content_artifacts = cch._save_artifact(download_result_mock, ra2)
    c2 = Content.objects.get(pk=c2.pk)
    assert ra1.content_artifact.relative_path in new_content_artifacts
    assert ra2.content_artifact.relative_path in existing_content_artifacts
    new_artifact = new_content_artifacts[ra1.content_artifact.relative_path]
    existing_artifact = existing_content_artifacts[ra2.content_artifact.relative_path]
    assert new_artifact.artifact.pk == existing_artifact.artifact.pk
    assert c2._artifacts.get().pk == existing_artifact.artifact.pk


# Test pull through features
@pytest.fixture
def remote123(db):
    return Remote.objects.create(name="123", url="https://123")


@pytest.fixture
def request123():
    return Mock(match_info={"path": "c123"})


# pytest-django fixtures does not work when testing async code
async def create_artifact(tmp_path):
    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text(str(tmp_file))
    artifact = Artifact.init_and_validate(str(tmp_file))
    await artifact.asave()
    return artifact


async def create_content():
    return await Content.objects.acreate()


async def create_content_artifact(content):
    return await ContentArtifact.objects.acreate(
        artifact=None, content=content, relative_path="c123"
    )


async def create_remote():
    return await Remote.objects.acreate(name=str(uuid.uuid4()), url="https://123")


async def create_remote_artifact(remote, ca):
    return await RemoteArtifact.objects.acreate(
        remote=remote, url="https://123/c123", content_artifact=ca
    )


async def create_repository():
    return await Repository.objects.acreate(name=str(uuid.uuid4()))


async def create_distribution(remote, repository=None):
    name = str(uuid.uuid4())
    return await Distribution.objects.acreate(
        name=name, base_path=name, remote=remote, repository=repository
    )


async def _add_content_to_new_version(repo, content):
    """Add ``content`` to a new complete version of ``repo`` and return that version."""
    repo.CONTENT_TYPES = [Content]

    def _add():
        with repo.new_version() as version:
            version.add_content(Content.objects.filter(pk=content.pk))
        return repo.latest_version()

    return await sync_to_async(_add)()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_remote_artifact_exists(request123, tmp_path):
    """Remote Artifact already exists, stream or serve associated content."""
    handler = Handler()
    handler._stream_content_artifact = AsyncMock()

    # Setup content w/ remote artifact
    content = await create_content()
    ca = await create_content_artifact(content)
    remote = await create_remote()
    await create_remote_artifact(remote, ca)
    distro = await create_distribution(remote)

    # Check that the handler finds the on-demand CA and calls the stream method
    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]

        # Manually save artifact for content_artifact
        tmp_file = tmp_path / str(uuid.uuid4())
        tmp_file.write_text(str(tmp_file))
        artifact = Artifact.init_and_validate(str(tmp_file))
        await artifact.asave()

        ca.artifact = artifact
        await ca.asave()
        handler._serve_content_artifact = AsyncMock()

        # Check that the handler finds the CA and calls the serve method
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._serve_content_artifact.assert_called_once()
        assert ca in handler._serve_content_artifact.call_args[0]
    finally:
        # Cleanup since this test isn't using fixtures
        await content.adelete()
        await remote.adelete()
        await distro.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_new_remote_artifacts(request123, monkeypatch):
    """Remote Artifact doesn't exist, create and stream content."""
    handler = Handler()
    handler._stream_remote_artifact = AsyncMock()

    remote = await create_remote()
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=Content))
    distro = await create_distribution(remote)

    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        remote.get_remote_artifact_content_type.assert_called_once_with("c123")
        handler._stream_remote_artifact.assert_called_once()

        args, kwargs = handler._stream_remote_artifact.call_args
        assert kwargs.get("save_artifact", None) is True
        ra = args[2]
        assert isinstance(ra, RemoteArtifact)
        assert ra.remote == remote
        assert ra.url == f"{remote.url}/c123"
        assert ra.content_artifact.relative_path == "c123"
    finally:
        await remote.adelete()
        await distro.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_metadata_file(request123, monkeypatch):
    """Requested path is for a metadata file. Don't save response."""
    handler = Handler()
    handler._stream_remote_artifact = AsyncMock()

    remote = await create_remote()
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=None))
    distro = await create_distribution(remote)

    try:
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        remote.get_remote_artifact_content_type.assert_called_once_with("c123")
        handler._stream_remote_artifact.assert_called_once()

        _, kwargs = handler._stream_remote_artifact.call_args
        assert kwargs.get("save_artifact", None) is False
    finally:
        await remote.adelete()
        await distro.adelete()


def test_pull_through_save_single_artifact_content(
    remote123, request123, download_result_mock, monkeypatch
):
    """Ensure single-artifact content is properly saved on pull-through."""
    handler = Handler()
    remote123.get_remote_artifact_content_type = Mock(return_value=Content)
    content_init_mock = Mock(return_value=Content())
    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", content_init_mock)
    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)

    # Content is saved during handler._save_artifact
    content_artifacts = handler._save_artifact(download_result_mock, ra, request=request123)
    artifact = content_artifacts[ra.content_artifact.relative_path].artifact

    remote123.get_remote_artifact_content_type.assert_called_once_with("c123")
    content_init_mock.assert_called_once_with(artifact, "c123")

    # Assert the CA and RA are properly saved
    ca = artifact.content_memberships.first()
    assert ca.content is not None
    assert ca.relative_path == "c123"
    ra = RemoteArtifact.objects.filter(
        url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca
    ).first()
    assert ra is not None


def test_pull_through_save_multi_artifact_content(
    remote123, request123, download_result_mock, monkeypatch, tmp_path
):
    """Ensure multi-artifact content is properly saved on pull-through."""
    handler = Handler()
    remote123.get_remote_artifact_content_type = Mock(return_value=Content)

    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text(str(tmp_file))
    artifact123 = Artifact.init_and_validate(str(tmp_file))
    artifact123.save()

    def content_init(art, path):
        return Content(), {path: artifact123, path + "abc": art}

    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", content_init)
    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)

    content_artifacts = handler._save_artifact(download_result_mock, ra, request123)
    ca1 = content_artifacts["c123"]
    ca2 = content_artifacts["c123abc"]
    assert ca1.content is not None
    assert ca2.content == ca1.content
    assert ca1.artifact == artifact123

    artifacts = set(ca1.content._artifacts.all())
    assert len(artifacts) == 2
    assert {ca2.artifact, artifact123} == artifacts


def test_pull_through_save_single_artifact_on_demand_content(
    remote123, request123, download_result_mock, monkeypatch
):
    """Ensure single-artifact content is properly saved on pull-through."""
    handler = Handler()
    remote123.get_remote_artifact_content_type = Mock(return_value=Content)
    content = Content.objects.create()
    content.save = Mock(side_effect=IntegrityError)
    content_init_mock = Mock(return_value=content)
    monkeypatch.setattr(Content, "init_from_artifact_and_relative_path", content_init_mock)
    monkeypatch.setattr(Content.objects, "get", Mock(return_value=content))
    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)

    # Content is saved during handler._save_artifact
    content_artifacts = handler._save_artifact(download_result_mock, ra, request=request123)
    artifact = content_artifacts[ra.content_artifact.relative_path].artifact

    remote123.get_remote_artifact_content_type.assert_called_once_with("c123")
    content_init_mock.assert_called_once_with(artifact, "c123")
    content.save.assert_called_once()
    Content.objects.get.assert_called_once()

    # Assert the CA and RA are properly saved
    ca = artifact.content_memberships.first()
    assert ca.content == content
    assert ca.relative_path == "c123"
    ra = RemoteArtifact.objects.filter(
        url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca
    ).first()
    assert ra is not None

    # Test on-demand were CA is updated with downloaded artifact
    ra.delete()
    ca.artifact = None
    ca.save()

    ca = ContentArtifact(relative_path="c123")
    ra = RemoteArtifact(url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca)
    content_artifacts = handler._save_artifact(download_result_mock, ra, request=request123)
    assert artifact == content_artifacts[ra.content_artifact.relative_path].artifact

    # Assert the CA and RA are properly saved
    ca = artifact.content_memberships.first()
    assert ca.content == content
    assert ca.relative_path == "c123"
    ra = RemoteArtifact.objects.filter(
        url=f"{remote123.url}/c123", remote=remote123, content_artifact=ca
    ).first()
    assert ra is not None


@pytest.mark.django_db
def test_handle_checkpoint_listing(
    monkeypatch,
    checkpoint_distribution,
    checkpoint_publication_1,
    noncheckpoint_publication,
    checkpoint_publication_2,
):
    """Checkpoint listing is generated correctly."""
    # Extract the pulp_created timestamps
    checkpoint_pub_1_ts = Handler._format_checkpoint_timestamp(
        checkpoint_publication_1.pulp_created
    )
    noncheckpoint_pub_ts = Handler._format_checkpoint_timestamp(
        noncheckpoint_publication.pulp_created
    )
    checkpoint_pub_2_ts = Handler._format_checkpoint_timestamp(
        checkpoint_publication_2.pulp_created
    )

    # Mock the render_html function to capture the checkpoint list
    original_render_html = Handler.render_html
    checkpoint_list = None

    def mock_render_html(directory_list, dates=None, path=None):
        nonlocal checkpoint_list
        html = original_render_html(directory_list, dates=dates, path=path)
        checkpoint_list = directory_list
        return html

    render_html_mock = Mock(side_effect=mock_render_html)
    monkeypatch.setattr(Handler, "render_html", render_html_mock)

    with pytest.raises(CheckpointListings):
        Handler._select_checkpoint_publication(checkpoint_distribution, "")
    assert len(checkpoint_list) == 2
    assert f"{checkpoint_pub_1_ts}/" in checkpoint_list, (
        f"{checkpoint_pub_1_ts} not found in error body"
    )
    assert f"{checkpoint_pub_2_ts}/" in checkpoint_list, (
        f"{checkpoint_pub_2_ts} not found in error body"
    )
    assert f"{noncheckpoint_pub_ts}/" not in checkpoint_list, (
        f"{noncheckpoint_pub_ts} found in error body"
    )


@pytest.mark.django_db
def test_handle_checkpoint_exact_ts(
    checkpoint_distribution,
    checkpoint_publication_1,
    noncheckpoint_publication,
    checkpoint_publication_2,
):
    """Checkpoint is correctly served when using exact timestamp."""
    checkpoint_pub_2_ts = Handler._format_checkpoint_timestamp(
        checkpoint_publication_2.pulp_created
    )
    publication = Handler._select_checkpoint_publication(
        checkpoint_distribution, f"{checkpoint_pub_2_ts}/"
    )

    assert publication is not None
    assert publication == checkpoint_publication_2


@pytest.mark.django_db
def test_handle_checkpoint_invalid_ts(
    checkpoint_distribution,
    checkpoint_publication_1,
):
    """Invalid checkpoint timestamp raises PathNotResolved."""
    with pytest.raises(PathNotResolved):
        Handler._select_checkpoint_publication(checkpoint_distribution, "99990115T181699Z/")

    with pytest.raises(PathNotResolved):
        Handler._select_checkpoint_publication(checkpoint_distribution, "invalid_ts/")


@pytest.mark.django_db
def test_handle_checkpoint_arbitrary_ts(
    checkpoint_distribution,
    checkpoint_publication_1,
    noncheckpoint_publication,
    checkpoint_publication_2,
):
    """Checkpoint is correctly served when using an arbitrary timestamp."""
    request_ts = Handler._format_checkpoint_timestamp(
        checkpoint_publication_1.pulp_created + timedelta(seconds=3)
    )
    with pytest.raises(HTTPMovedPermanently) as excinfo:
        Handler._select_checkpoint_publication(checkpoint_distribution, f"{request_ts}/")
    redirect_location = excinfo.value.location

    with pytest.raises(HTTPMovedPermanently) as excinfo:
        Handler._redirect_sub_path(
            f"{checkpoint_distribution.base_path}"
            f"/{Handler._format_checkpoint_timestamp(checkpoint_publication_1.pulp_created)}/"
        )
    expected_location = excinfo.value.location

    assert redirect_location == expected_location, (
        f"Unexpected redirect location: {redirect_location}"
    )


@pytest.mark.django_db
def test_handle_checkpoint_before_first_ts(
    checkpoint_distribution,
    checkpoint_publication_1,
):
    """Checkpoint timestamp before the first checkpoint raises PathNotResolved.."""
    request_ts = Handler._format_checkpoint_timestamp(
        checkpoint_publication_1.pulp_created - timedelta(seconds=1)
    )
    with pytest.raises(PathNotResolved):
        Handler._select_checkpoint_publication(checkpoint_distribution, f"{request_ts}/")


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_pull_through_repository_add(request123, monkeypatch):
    """Test that repository adding is called when supported."""
    handler = Handler()
    handler._stream_content_artifact = AsyncMock()

    content = await create_content()
    ca = await create_content_artifact(content)
    remote = await create_remote()
    await create_remote_artifact(remote, ca)
    repo = await create_repository()
    monkeypatch.setattr(Remote, "get_remote_artifact_content_type", Mock(return_value=Content))
    monkeypatch.setattr(Repository, "async_pull_through_add_content", AsyncMock())
    distro = await create_distribution(remote, repository=repo)

    try:
        # Assert with Repository.PULL_THROUGH_SUPPORTED=False the method isn't called
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]
        repo.async_pull_through_add_content.assert_not_called()

        # Now set PULL_THROUGH_SUPPORTED=True and see the method is called with CA
        monkeypatch.setattr(Repository, "PULL_THROUGH_SUPPORTED", True)
        handler._stream_content_artifact.reset_mock()
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]
        repo.async_pull_through_add_content.assert_called_once()
        assert ca in repo.async_pull_through_add_content.call_args[0]
    finally:
        await content.adelete()
        await repo.adelete()
        await remote.adelete()
        await distro.adelete()


@pytest_asyncio.fixture
async def app_status(monkeypatch):
    monkeypatch.setattr(AppStatus.objects, "_current_app_status", None)
    app_status = await AppStatus.objects.acreate(app_type="api", name="test_runner")
    yield app_status
    await app_status.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
@pytest.mark.parametrize("repeat", (1, 2))
async def test_app_status_fixture_is_reusable(app_status, repeat):
    # testing this because AppStatus handles global process state
    assert app_status


def test_render_html_colon_in_name():
    """Links with colons in the name should use './' prefix to avoid being treated as a scheme."""
    html = Handler.render_html(["copr-pull-requests:pr:3825/"])
    assert '<a href="./copr-pull-requests:pr:3825/">copr-pull-requests:pr:3825/</a>' in html


def test_render_html_normal_name():
    """Normal directory names should also get the './' prefix."""
    html = Handler.render_html(["simple-dir/"])
    assert '<a href="./simple-dir/">simple-dir/</a>' in html


_LAST_MODIFIED = datetime(2020, 1, 1, tzinfo=dt_timezone.utc)
_LAST_MODIFIED_HTTP = http_date(_LAST_MODIFIED.timestamp())
_IF_MODIFIED_SINCE_AFTER = http_date(datetime(2021, 1, 1, tzinfo=dt_timezone.utc).timestamp())
_IF_MODIFIED_SINCE_BEFORE = http_date(datetime(2019, 1, 1, tzinfo=dt_timezone.utc).timestamp())
_CACHE_CONTROL = "public, max-age=0, must-revalidate"


class _UnsatisfiableRange:
    @property
    def start(self):
        raise ValueError()

    stop = None


def _request(*, if_modified_since=None, http_range=None):
    return Mock(
        method="GET",
        http_range=http_range if http_range is not None else Mock(start=None, stop=None),
        headers={"If-Modified-Since": if_modified_since} if if_modified_since else {},
    )


def _ca(*, artifact=True):
    ca = Mock()
    ca.relative_path = "file.iso"
    if artifact:
        ca.artifact.file.size = 7
        ca.artifact.file.name = "artifacts/obj"
    else:
        ca.artifact = None
    return ca


def _handler_with_built_response(monkeypatch, built=None):
    handler = Handler()
    ca = _ca()
    if built is None:
        built = Mock(headers={"Cache-Control": _CACHE_CONTROL}, status=200)
    monkeypatch.setattr(handler, "_build_response_from_content_artifact", Mock(return_value=built))
    return handler, ca, built


def _membership_pulp_created(version, content):
    return (
        version._content_relationships()
        .filter(content_id=content.pk)
        .values_list("pulp_created", flat=True)
        .get()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "if_modified_since, last_modified, cache_enabled, expect_304",
    [
        (None, _LAST_MODIFIED, False, False),
        (_IF_MODIFIED_SINCE_AFTER, _LAST_MODIFIED, False, True),
        (_IF_MODIFIED_SINCE_BEFORE, _LAST_MODIFIED, False, False),
        (_IF_MODIFIED_SINCE_AFTER, None, False, False),
        (_IF_MODIFIED_SINCE_AFTER, _LAST_MODIFIED, True, False),
    ],
    ids=["no-if-modified-since", "fresh", "stale", "no-timestamp", "cache-on"],
)
async def test_serve_content_artifact_if_modified_since(
    monkeypatch, if_modified_since, last_modified, cache_enabled, expect_304
):
    """Filesystem responses stamp Last-Modified.

    A matching If-Modified-Since is 304 unless the cache is on.
    """
    handler, ca, built = _handler_with_built_response(monkeypatch)

    with override_settings(CACHE_ENABLED=cache_enabled):
        if expect_304:
            with pytest.raises(HTTPNotModified) as exc:
                await handler._serve_content_artifact(
                    ca,
                    {},
                    _request(if_modified_since=if_modified_since),
                    last_modified=last_modified,
                )
            assert exc.value.headers["Last-Modified"] == _LAST_MODIFIED_HTTP
            assert exc.value.headers["Cache-Control"] == _CACHE_CONTROL
        else:
            response = await handler._serve_content_artifact(
                ca,
                {},
                _request(if_modified_since=if_modified_since),
                last_modified=last_modified,
            )
            assert response is built
            if last_modified is None:
                assert "Last-Modified" not in response.headers
            else:
                assert response.headers["Last-Modified"] == _LAST_MODIFIED_HTTP


def test_response_headers_sets_cache_control():
    """All content responses instruct edge caches to revalidate on every use."""
    headers = Handler.response_headers("path/to/file.iso")
    assert headers["Cache-Control"] == _CACHE_CONTROL


@pytest.mark.asyncio
async def test_serve_content_artifact_redirect_is_not_304(monkeypatch):
    """Object-storage 302s never get a Pulp Last-Modified.

    A matching If-Modified-Since must not 304.
    """
    redirect = HTTPFound(
        "http://example.test/redirect",
        headers={"Cache-Control": _CACHE_CONTROL},
    )
    handler, ca, _built = _handler_with_built_response(monkeypatch, built=redirect)

    with override_settings(CACHE_ENABLED=False):
        with pytest.raises(HTTPFound) as exc:
            await handler._serve_content_artifact(
                ca,
                {},
                _request(if_modified_since=_IF_MODIFIED_SINCE_AFTER),
                last_modified=_LAST_MODIFIED,
            )

    assert "Last-Modified" not in exc.value.headers
    assert "Cache-Control" not in exc.value.headers


@pytest.mark.asyncio
async def test_serve_content_artifact_304_beats_unsatisfiable_range(monkeypatch):
    """A matching If-Modified-Since 304s even when Range would otherwise be 416."""
    handler, ca, _built = _handler_with_built_response(monkeypatch)
    request = _request(if_modified_since=_IF_MODIFIED_SINCE_AFTER, http_range=_UnsatisfiableRange())

    with override_settings(CACHE_ENABLED=False):
        with pytest.raises(HTTPNotModified) as exc:
            await handler._serve_content_artifact(ca, {}, request, last_modified=_LAST_MODIFIED)

    assert exc.value.status == 304
    assert exc.value.headers["Last-Modified"] == _LAST_MODIFIED_HTTP


@pytest.mark.asyncio
async def test_on_demand_conditional_before_stream(monkeypatch):
    """On-demand units 304 before the remote fetch; otherwise the stream carries Last-Modified."""
    handler = Handler()
    ca = _ca(artifact=False)
    monkeypatch.setattr(handler, "_content_last_modified", AsyncMock(return_value=_LAST_MODIFIED))
    handler._stream_content_artifact = AsyncMock(return_value="streamed")

    with pytest.raises(HTTPNotModified) as exc:
        await handler._serve_ca(
            ca,
            {"Cache-Control": _CACHE_CONTROL},
            Mock(headers={"If-Modified-Since": _LAST_MODIFIED_HTTP}),
            repository_version="rv",
        )
    handler._stream_content_artifact.assert_not_awaited()
    assert exc.value.headers["Last-Modified"] == _LAST_MODIFIED_HTTP
    assert exc.value.headers["Cache-Control"] == _CACHE_CONTROL

    result = await handler._serve_ca(ca, {}, Mock(headers={}), repository_version="rv")
    assert result == "streamed"
    _, stream_response, stream_ca = handler._stream_content_artifact.call_args.args
    assert stream_ca is ca
    assert stream_response.headers["Last-Modified"] == _LAST_MODIFIED_HTTP


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_content_last_modified_from_repository_membership():
    """Last-Modified is RepositoryContent.pulp_created for the served version, else omitted."""
    repo = await create_repository()
    content = await create_content()
    other = await create_content()
    publication = None
    try:
        ca = await create_content_artifact(content)
        handler = Handler()
        assert await handler._content_last_modified(ca) is None

        v1 = await _add_content_to_new_version(repo, content)
        expected = await sync_to_async(_membership_pulp_created)(v1, content)
        assert await handler._content_last_modified(ca, repository_version=v1) == expected

        publication = await sync_to_async(Publication.objects.create)(repository_version=v1)
        assert await handler._content_last_modified(ca, publication=publication) == expected

        def _add_other():
            with repo.new_version() as version:
                version.add_content(Content.objects.filter(pk=other.pk))
            return repo.latest_version()

        v2 = await sync_to_async(_add_other)()
        assert await handler._content_last_modified(ca, repository_version=v2) == expected

        def _remove():
            with repo.new_version() as version:
                version.remove_content(Content.objects.filter(pk=content.pk))
            return repo.latest_version()

        v3 = await sync_to_async(_remove)()
        assert await handler._content_last_modified(ca, repository_version=v3) is None
    finally:
        if publication is not None:
            await publication.adelete()
        await repo.adelete()
        await content.adelete()
        await other.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_async_pull_through_add(ca1, monkeypatch, app_status):
    set_guid(uuid.uuid4())  # required for creating a task, no easily mockable
    monkeypatch.setattr(
        "pulpcore.tasking.tasks.async_are_resources_available", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("pulpcore.tasking.tasks.wakeup_worker", Mock())

    repo = await Repository.objects.acreate(name=str(uuid.uuid4()))
    try:
        task = await repo.async_pull_through_add_content(ca1)
        assert task.state == TASK_STATES.COMPLETED
    except Exception as e:
        task = None
        assert e is None
    finally:
        clear_guid()
        await repo.adelete()
        if task:
            await task.adelete()
