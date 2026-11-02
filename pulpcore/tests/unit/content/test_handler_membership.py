"""Database-backed checks of the content handler's repository membership lookups."""

import uuid
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import make_mocked_request
from aiohttp.web_exceptions import HTTPMovedPermanently
from asgiref.sync import sync_to_async
from django.db import connection
from django.test.utils import CaptureQueriesContext

from pulpcore.content.handler import Handler, PathNotResolved, _current_distribution
from pulpcore.plugin.models import Content, ContentArtifact, Distribution, Repository

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db]


@sync_to_async
def build_repository(*steps):
    """
    Create a repository with one version per step; return (repository, versions, contents).

    Each step is (paths_to_add, paths_to_remove). Versions are built through new_version() so
    both the content_ids array and the RepositoryContent intervals describe the membership.
    """
    repository = Repository.objects.create(name=str(uuid.uuid4()))
    repository.CONTENT_TYPES = [Content]
    contents = {}
    versions = []
    for add, remove in steps:
        for path in add:
            content = Content.objects.create(pulp_type="core.content")
            ContentArtifact.objects.create(content=content, relative_path=path)
            contents[path] = content
        with repository.new_version() as version:
            version.add_content(Content.objects.filter(pk__in=[contents[p].pk for p in add]))
            version.remove_content(Content.objects.filter(pk__in=[contents[p].pk for p in remove]))
        versions.append(version)
    return repository, versions, contents


async def create_distribution(repo_version):
    name = str(uuid.uuid4())
    return await Distribution.objects.acreate(
        name=name, base_path=name, repository_version=repo_version
    )


@pytest.fixture
def serve(monkeypatch):
    """Serve a path from a distribution; return the ContentArtifact the handler picked."""

    async def _serve(distribution, path):
        served = AsyncMock(side_effect=lambda *args: next(a for a in args if hasattr(a, "pk")))
        monkeypatch.setattr(Handler, "_serve_content_artifact", served)
        monkeypatch.setattr(Handler, "_stream_content_artifact", served)
        monkeypatch.setattr(Handler, "_set_last_modified_header", AsyncMock())
        _current_distribution.set(distribution)
        full_path = f"{distribution.base_path}/{path}"
        request = make_mocked_request("GET", f"/pulp/content/{full_path}")
        return await Handler()._match_and_stream(full_path, request)

    return _serve


async def capture_sql(awaitable):
    """Capture SQL run by the ORM's worker thread while awaiting awaitable."""
    context = CaptureQueriesContext(connection)
    await sync_to_async(context.__enter__)()
    try:
        result = await awaitable
    finally:
        await sync_to_async(context.__exit__)(None, None, None)
    # captured_queries reads the calling thread's connection, so read it in the worker thread.
    queries = await sync_to_async(lambda: [q["sql"] for q in context.captured_queries])()
    return result, queries


def contentartifact_sql(queries):
    return [sql for sql in queries if 'FROM "core_contentartifact"' in sql]


async def test_list_directory_lists_only_version_content():
    """Entries come only from the listed version, not from other repositories or no repository."""
    _, (version,), _ = await build_repository(
        (["org/a/a-1.0.jar", "org/b/index.html", "top.txt"], [])
    )
    _, (other_version,), _ = await build_repository((["org/c/c-1.0.jar", "org/a/a-2.0.jar"], []))
    # Exists as a ContentArtifact, but belongs to no repository version.
    orphan = await Content.objects.acreate(pulp_type="core.content")
    await ContentArtifact.objects.acreate(content=orphan, relative_path="org/z.jar")

    directory_list, _, _ = await Handler().list_directory(version, None, "org/")
    assert directory_list == {"a/", "b/"}

    other_list, _, _ = await Handler().list_directory(other_version, None, "org/")
    assert other_list == {"c/", "a/"}


async def test_list_directory_excludes_removed_content():
    """Content removed in a later version is listed only for the versions that contained it."""
    _, (version_1, version_2), _ = await build_repository(
        (["pkg/keep.rpm", "pkg/gone.rpm"], []),
        (["pkg/new.rpm"], ["pkg/gone.rpm"]),
    )

    listed_1, _, _ = await Handler().list_directory(version_1, None, "pkg/")
    listed_2, _, _ = await Handler().list_directory(version_2, None, "pkg/")

    assert listed_1 == {"keep.rpm", "gone.rpm"}
    assert listed_2 == {"keep.rpm", "new.rpm"}


async def test_list_directory_lists_dotted_directories():
    _, (version,), _ = await build_repository(
        (["12.1.12/index.html", "12.1.12/a.txt", "top.txt"], [])
    )

    root, _, _ = await Handler().list_directory(version, None, "")
    nested, _, _ = await Handler().list_directory(version, None, "12.1.12/")

    assert root == {"12.1.12/", "top.txt"}
    assert nested == {"index.html", "a.txt"}


async def test_list_directory_query_uses_correlated_exists():
    _, (version,), _ = await build_repository((["org/a/a-1.0.jar"], []))

    _, queries = await capture_sql(Handler().list_directory(version, None, "org/"))

    (sql,) = contentartifact_sql(queries)
    assert "EXISTS" in sql
    assert "unnest" not in sql.lower()
    assert "content_ids" not in sql


async def test_file_lookup_serves_only_version_content(serve):
    _, (version,), _ = await build_repository((["org/a.jar"], []))
    await build_repository((["org/other.jar"], []))
    distribution = await create_distribution(version)

    served = await serve(distribution, "org/a.jar")
    assert served.relative_path == "org/a.jar"

    # Another repository's content is never served, even though the ContentArtifact exists.
    with pytest.raises(PathNotResolved):
        await serve(distribution, "org/other.jar")


async def test_file_lookup_does_not_serve_removed_content(serve):
    _, (version_1, version_2), _ = await build_repository(
        (["pkg/gone.rpm"], []),
        ([], ["pkg/gone.rpm"]),
    )

    served = await serve(await create_distribution(version_1), "pkg/gone.rpm")
    assert served.relative_path == "pkg/gone.rpm"
    with pytest.raises(PathNotResolved):
        await serve(await create_distribution(version_2), "pkg/gone.rpm")


async def test_file_lookup_query_uses_correlated_exists(serve):
    _, (version,), _ = await build_repository((["org/a.jar"], []))
    distribution = await create_distribution(version)

    _, queries = await capture_sql(serve(distribution, "org/a.jar"))

    lookups = contentartifact_sql(queries)
    assert lookups
    for sql in lookups:
        assert "EXISTS" in sql
        assert "unnest" not in sql.lower()
        assert "content_ids" not in sql


@pytest.mark.parametrize("path", ["12.1.12/", "12.1.12"])
async def test_index_html_is_served_for_dotted_directory(serve, path):
    """A dotted final segment can still be a directory holding index.html."""
    _, (version,), _ = await build_repository((["12.1.12/index.html", "12.1.12/a.txt"], []))
    distribution = await create_distribution(version)

    served = await serve(distribution, path)

    assert served.relative_path == "12.1.12/index.html"


async def test_dotted_directory_without_index_redirects_to_listing(serve):
    _, (version,), _ = await build_repository((["12.1.12/a.txt"], []))
    distribution = await create_distribution(version)

    with pytest.raises(HTTPMovedPermanently):
        await serve(distribution, "12.1.12")


async def test_index_probe_ignores_other_repository_index(serve):
    _, (version,), _ = await build_repository((["docs/page.html"], []))
    await build_repository((["docs/index.html"], []))
    distribution = await create_distribution(version)

    with pytest.raises(HTTPMovedPermanently):
        # No index.html in this version, so the directory is listed instead.
        await serve(distribution, "docs")


async def test_index_probe_is_existence_only_with_limit(serve):
    _, (version,), _ = await build_repository((["docs/index.html"], []))
    distribution = await create_distribution(version)

    _, queries = await capture_sql(serve(distribution, "docs/"))

    probe = next(
        sql for sql in contentartifact_sql(queries) if "relative_path\" = 'docs/index.html'" in sql
    )
    assert probe.startswith('SELECT "core_contentartifact"."pulp_id"')
    assert probe.rstrip().endswith("LIMIT 1")
    assert "EXISTS" in probe
    assert "unnest" not in probe.lower()
