from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction

from pulpcore.app.models import RepositoryContent, RepositoryMembership, RepositoryVersion
from pulpcore.exceptions import ResourceImmutableError
from pulpcore.plugin.models import Content, Repository


@pytest.fixture
def repository(db):
    repository = Repository.objects.create(name=uuid4(), versioned=False)
    repository.CONTENT_TYPES = [Content]
    return repository


@pytest.fixture
def hooks(repository):
    """Replace the repository hooks with mocks that record the order they are called in."""
    calls = []
    for name in ("initialize_new_version", "finalize_new_version", "on_new_version"):
        setattr(repository, name, Mock(side_effect=lambda v, name=name: calls.append(name)))
    repository.invalidate_cache = Mock(side_effect=lambda: calls.append("invalidate_cache"))
    return calls


@pytest.fixture
def content_pks(db):
    contents = [Content(pulp_type="core.content") for _ in range(0, 4)]
    Content.objects.bulk_create(contents)
    return [content.pk for content in contents]


def _add_rows(repository, pks):
    RepositoryContent.objects.bulk_create(
        [RepositoryContent(repository=repository, content_id=pk) for pk in pks]
    )


def _pks(qs):
    return set(qs.values_list("pk", flat=True))


def _qs(*pks):
    return Content.objects.filter(pk__in=pks)


def _rows(repository):
    return set(
        RepositoryContent.objects.filter(repository=repository).values_list("content_id", flat=True)
    )


def test_versioned_repository_gets_initial_version(db):
    """Verify that repositories are versioned by default and still get version 0."""
    repository = Repository.objects.create(name=uuid4())
    assert repository.versioned is True
    assert repository.versions.count() == 1


def test_unversioned_repository_has_no_versions(repository):
    """Verify that an unversioned repository is created without any version row."""
    assert repository.versions.count() == 0


def test_versioned_cannot_change(repository):
    """Verify that `versioned` cannot be changed after creation."""
    repository.versioned = True
    with pytest.raises(ValueError):
        repository.save()


def test_new_version_returns_writable_membership(repository):
    """Verify that `new_version()` returns a writable membership and creates no version."""
    version = repository.new_version()
    assert isinstance(version, RepositoryMembership)
    assert version.complete is False
    assert repository.versions.count() == 0


def test_new_version_rejects_base_version(repository):
    """Verify that `base_version` is rejected, since there are no versions to use as a base."""
    versioned = Repository.objects.create(name=uuid4())
    with pytest.raises(ValueError):
        repository.new_version(base_version=versioned.latest_version())


def test_latest_version_returns_read_only_membership(repository):
    """Verify that `latest_version()` returns a read-only membership."""
    version = repository.latest_version()
    assert isinstance(version, RepositoryMembership)
    assert version.complete is True


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_alatest_version_returns_read_only_membership():
    """Verify that `alatest_version()` returns a read-only membership."""
    repository = await Repository.objects.acreate(name=uuid4(), versioned=False)
    version = await repository.alatest_version()
    assert isinstance(version, RepositoryMembership)
    assert version.complete is True


def test_unversioned_membership_is_unique(repository, content_pks):
    """Verify that the same content cannot be in one unversioned repository twice."""
    _add_rows(repository, content_pks[:1])
    with pytest.raises(IntegrityError), transaction.atomic():
        _add_rows(repository, content_pks[:1])


def test_same_content_in_two_unversioned_repositories(repository, content_pks):
    """Verify that the same content can be in different unversioned repositories."""
    other = Repository.objects.create(name=uuid4(), versioned=False)
    _add_rows(repository, content_pks[:1])
    _add_rows(other, content_pks[:1])
    assert RepositoryContent.objects.filter(content_id=content_pks[0]).count() == 2


def test_compatibility_attributes(repository):
    """
    Verify the attributes kept for compatibility with `RepositoryVersion`, and that `number` and
    `pk` are absent.
    """
    version = repository.latest_version()
    assert version.DoesNotExist is RepositoryVersion.DoesNotExist
    assert version.base_version is None
    assert version.pulp_created is None
    # Dropped on purpose, so unexpected callers fail loudly.
    assert not hasattr(version, "number")
    assert not hasattr(version, "pk")


def test_content_reads_only_this_repository(repository, content_pks):
    """Verify that `content` only returns the content of this repository."""
    other = Repository.objects.create(name=uuid4(), versioned=False)
    _add_rows(repository, content_pks[:2])
    _add_rows(other, content_pks[2:])
    assert _pks(repository.latest_version().content) == set(content_pks[:2])


def test_get_content_narrows_given_queryset(repository, content_pks):
    """
    Verify that `get_content()` returns the intersection of the given queryset and the repository
    content.
    """
    _add_rows(repository, content_pks[:2])
    content_qs = Content.objects.filter(pk__in=content_pks[1:])
    assert _pks(repository.latest_version().get_content(content_qs)) == {content_pks[1]}


def test_contains(repository, content_pks):
    """Verify that `contains()` tells whether content is in the repository."""
    _add_rows(repository, content_pks[:1])
    version = repository.latest_version()
    assert version.contains(Content.objects.get(pk=content_pks[0]))
    assert not version.contains(Content.objects.get(pk=content_pks[1]))


def test_added_and_removed(repository, content_pks):
    """Verify that `added()` and `removed()` report the changes made through the instance."""
    version = repository.new_version()
    version._added = {content_pks[0]}
    version._removed = {content_pks[1]}
    assert _pks(version.added()) == {content_pks[0]}
    assert _pks(version.removed()) == {content_pks[1]}


def test_added_and_removed_ignore_base_version(repository, content_pks):
    """Verify that `added()` and `removed()` accept `base_version`, as `RepositoryVersion` does."""
    version = repository.new_version()
    version._added = {content_pks[0]}
    assert _pks(version.added(base_version=None)) == {content_pks[0]}
    assert _pks(version.removed(base_version=None)) == set()


def test_previous_is_state_before_changes(repository, content_pks):
    """Verify that `previous()` hides the additions and brings back the removals."""
    # Before: 0, 1. The operation added 2 and removed 1, so the rows are now 0, 2.
    _add_rows(repository, [content_pks[0], content_pks[2]])
    version = repository.new_version()
    version._added = {content_pks[2]}
    version._removed = {content_pks[1]}

    assert _pks(version.content) == {content_pks[0], content_pks[2]}
    assert _pks(version.previous().content) == {content_pks[0], content_pks[1]}


def test_writes_are_checked_before_writing(repository, content_pks):
    """
    Verify that read-only instances, wrong querysets and unsupported content types are rejected
    before anything is written.
    """
    read_only = repository.latest_version()
    with pytest.raises(ResourceImmutableError):
        read_only.add_content(_qs(content_pks[0]))
    with pytest.raises(ResourceImmutableError):
        read_only.remove_content(_qs(content_pks[0]))
    with pytest.raises(RuntimeError):
        with read_only:
            pass

    version = repository.new_version()
    with pytest.raises(AssertionError):
        version.add_content(Repository.objects.all())
    wrong_type = Content.objects.create(pulp_type="wrong.type")
    with pytest.raises(ValueError):
        version.add_content(_qs(wrong_type.pk))

    assert _rows(repository) == set()


def test_add_and_remove_content(repository, content_pks):
    """
    Verify that only new content is added and reported, and that absent content is ignored on
    removal.
    """
    _add_rows(repository, content_pks[:1])
    version = repository.new_version()

    version.add_content(_qs(*content_pks[:2]))
    assert _pks(version.added()) == {content_pks[1]}
    assert _rows(repository) == set(content_pks[:2])
    assert not RepositoryContent.objects.filter(
        repository=repository, version_added__isnull=False
    ).exists()

    version.remove_content(_qs(content_pks[0], content_pks[3]))
    assert _pks(version.removed()) == {content_pks[0]}
    assert _rows(repository) == {content_pks[1]}


def test_add_and_remove_in_one_operation(repository, content_pks):
    """
    Verify that adding then removing content, or removing then adding it, counts as no change.
    """
    _add_rows(repository, content_pks[:1])
    version = repository.new_version()

    version.add_content(_qs(content_pks[1]))
    version.remove_content(_qs(content_pks[1]))
    version.remove_content(_qs(content_pks[0]))
    version.add_content(_qs(content_pks[0]))

    assert _pks(version.added()) == set()
    assert _pks(version.removed()) == set()
    assert _rows(repository) == {content_pks[0]}


def test_set_content(repository, content_pks):
    """Verify that `set_content()` removes the extra content and adds the missing content."""
    _add_rows(repository, content_pks[:2])
    version = repository.new_version()
    version.set_content(_qs(*content_pks[1:3]))

    assert _rows(repository) == set(content_pks[1:3])
    assert _pks(version.added()) == {content_pks[2]}
    assert _pks(version.removed()) == {content_pks[0]}


def test_exit_with_changes(repository, content_pks, hooks):
    """
    Verify the order of the hooks and the cache invalidation when the operation changed content.
    """
    with repository.new_version() as version:
        version.add_content(_qs(content_pks[0]))

    assert hooks == [
        "initialize_new_version",
        "finalize_new_version",
        "on_new_version",
        "invalidate_cache",
    ]
    assert version.complete is True


def test_exit_without_changes(repository, content_pks, hooks):
    """
    Verify that `on_new_version()` and the cache invalidation are skipped when nothing changed.
    """
    _add_rows(repository, content_pks[:1])
    with repository.new_version() as version:
        version.add_content(_qs(content_pks[0]))

    assert hooks == ["initialize_new_version", "finalize_new_version"]
    assert version.complete is True


@pytest.mark.parametrize("failing", ("finalize", "block"))
def test_failure_keeps_changes(repository, content_pks, hooks, failing):
    """
    Verify that a failure keeps the written rows, invalidates the cache and skips
    `on_new_version()`.
    """
    if failing == "finalize":
        repository.finalize_new_version.side_effect = RuntimeError
    with pytest.raises(RuntimeError):
        with repository.new_version() as version:
            version.add_content(_qs(content_pks[0]))
            if failing == "block":
                raise RuntimeError

    repository.on_new_version.assert_not_called()
    repository.invalidate_cache.assert_called_once()
    assert _rows(repository) == {content_pks[0]}
    assert version.complete is True
