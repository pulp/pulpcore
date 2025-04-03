from datetime import timedelta
import pytest
import uuid

from unittest.mock import Mock, AsyncMock

from aiohttp.web_exceptions import HTTPMovedPermanently
from django.db import IntegrityError
from pulpcore.content.handler import Handler, CheckpointListings, PathNotResolved
from pulpcore.plugin.models import (
    Artifact,
    Content,
    ContentArtifact,
    Distribution,
    Remote,
    RemoteArtifact,
    Repository,
    RepositoryVersion,
    Publication,
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
    assert (
        f"{checkpoint_pub_1_ts}/" in checkpoint_list
    ), f"{checkpoint_pub_1_ts} not found in error body"
    assert (
        f"{checkpoint_pub_2_ts}/" in checkpoint_list
    ), f"{checkpoint_pub_2_ts} not found in error body"
    assert (
        f"{noncheckpoint_pub_ts}/" not in checkpoint_list
    ), f"{noncheckpoint_pub_ts} found in error body"


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

    assert (
        redirect_location == expected_location
    ), f"Unexpected redirect location: {redirect_location}"


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
    monkeypatch.setattr(Repository, "pull_through_add_content", Mock())
    distro = await create_distribution(remote, repository=repo)

    try:
        # Assert with Repository.PULL_THROUGH_SUPPORTED=False the method isn't called
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]
        repo.pull_through_add_content.assert_not_called()

        # Now set PULL_THROUGH_SUPPORTED=True and see the method is called with CA
        monkeypatch.setattr(Repository, "PULL_THROUGH_SUPPORTED", True)
        handler._stream_content_artifact.reset_mock()
        await handler._match_and_stream(f"{distro.base_path}/c123", request123)
        handler._stream_content_artifact.assert_called_once()
        assert ca in handler._stream_content_artifact.call_args[0]
        repo.pull_through_add_content.assert_called_once()
        assert ca in repo.pull_through_add_content.call_args[0]
    finally:
        await content.adelete()
        await repo.adelete()
        await remote.adelete()
        await distro.adelete()
