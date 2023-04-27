import pytest
from uuid import uuid4

from itertools import compress

from pulpcore.plugin.models import Content, Repository


def pks_of_next_qs(qs_generator):
    """Iterate qs_generator one step and return the list of pks in the qs."""
    return list(next(qs_generator).values_list("pk", flat=True))


@pytest.fixture
def repository(db):
    repository = Repository.objects.create(name=uuid4())
    repository.CONTENT_TYPES = [Content]
    return repository


@pytest.fixture
def content_pks(db):
    contents = [Content(pulp_type="core.content") for _ in range(0, 5)]
    Content.objects.bulk_create(contents)
    return sorted([content.pk for content in contents])


@pytest.fixture
def add_content(content_pks):
    def _add_content(version, mask):
        version.add_content(Content.objects.filter(pk__in=compress(content_pks, mask)))

    return _add_content


@pytest.fixture
def remove_content(content_pks):
    def _remove_content(version, mask):
        version.remove_content(Content.objects.filter(pk__in=compress(content_pks, mask)))

    return _remove_content


@pytest.fixture
def verify_content_sets(content_pks):
    def _verify_content_sets(version, current, added, removed, base_version=None):
        """
        Verify the content, added, and removed sets for a repository version.

        Args:
            version (pulpcore.app.models.RepositoryVersion): the version instance to verify
            current (list): "presence list" for content with respect to `content_pks`.
                For example, [1, 0, 1] means that content with content_pks[0], and
                content_pks[2] must be present, all other content must not be present.
            added (list): "presence list" for added content
            remove (list): "presence list" for removed content
            base_version (pulpcore.app.models.RepositoryVersion): optional base version to
                verify the difference to

        """
        current_pks = set(version.content.values_list("pk", flat=True))
        added_pks = set(version.added(base_version).values_list("pk", flat=True))
        removed_pks = set(version.removed(base_version).values_list("pk", flat=True))

        # There must never be content shown as added & removed
        assert added_pks.intersection(removed_pks) == set()

        assert current_pks == set(compress(content_pks, current))
        assert added_pks == set(compress(content_pks, added))
        assert removed_pks == set(compress(content_pks, removed))

    return _verify_content_sets


@pytest.mark.django_db
def test_add_and_remove_content(repository, add_content, remove_content, verify_content_sets):
    version0 = repository.latest_version()

    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 0])  # v1 == four content units 0-3

    with repository.new_version() as version2:
        remove_content(version2, [1, 1, 0, 0, 0])  # v2 == removed 2 first contents

    with repository.new_version() as version3:
        add_content(version3, [1, 0, 0, 0, 0])  # v3 == added first content

    verify_content_sets(version1, [1, 1, 1, 1, 0], [1, 1, 1, 1, 0], [0, 0, 0, 0, 0], version0)
    verify_content_sets(version2, [0, 0, 1, 1, 0], [0, 0, 1, 1, 0], [0, 0, 0, 0, 0], version0)
    verify_content_sets(version2, [0, 0, 1, 1, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0], version1)
    verify_content_sets(version3, [1, 0, 1, 1, 0], [1, 0, 1, 1, 0], [0, 0, 0, 0, 0], version0)
    verify_content_sets(version3, [1, 0, 1, 1, 0], [0, 0, 0, 0, 0], [0, 1, 0, 0, 0], version1)
    verify_content_sets(version3, [1, 0, 1, 1, 0], [1, 0, 0, 0, 0], [0, 0, 0, 0, 0], version2)


def test_add_remove(repository, add_content, remove_content, verify_content_sets):
    """Verify that adding and then removing content units is handled properly."""
    version0 = repository.latest_version()

    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 1])
        verify_content_sets(version1, [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [0, 0, 0, 0, 0])

        remove_content(version1, [1, 1, 1, 1, 1])
        verify_content_sets(version1, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0])

    assert repository.latest_version() == version0, "Empty version1 must not exist."


def test_remove_add(repository, add_content, remove_content, verify_content_sets):
    """Verify that removing and then adding content units is handled properly."""
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 1])

    with repository.new_version() as version2:
        remove_content(version2, [1, 1, 1, 1, 1])
        verify_content_sets(version2, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 1, 1, 1])

        add_content(version2, [1, 1, 1, 1, 1])
        verify_content_sets(version2, [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0])

    assert repository.latest_version() == version1, "Empty version2 must not exist."


def test_multiple_adds_and_removes(repository, add_content, remove_content, verify_content_sets):
    """Verify that adding/removing content multiple times is handled properly.

    Additionally, verify that other content (untouched, simple add, simple
    remove) is not influenced and behaves as expected.
    """
    # v1 == content id 0, 2, and 4
    with repository.new_version() as version1:
        add_content(version1, [1, 0, 1, 0, 1])

    # v2 version is created in multiple steps:
    #
    # |       | content id                                 |
    # |       | 0      | 1      | 2      | 3      | 4      |
    # | step1 |        |        | remove |        | remove |
    # | step2 |        | add    |        | add    | add    |
    # | step3 |        |        |        | remove | remove |
    # | step4 |        |        |        | add    |        |
    #
    # Expected outcome after step 4:
    # content: 0, 1, 3
    # added: 1, 3
    # removed: 2, 4
    with repository.new_version() as version2:
        # Content must be that of version1:
        verify_content_sets(version2, [1, 0, 1, 0, 1], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0])

        # step 1
        remove_content(version2, [0, 0, 1, 0, 1])
        verify_content_sets(version2, [1, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 1, 0, 1])

        # step 2
        add_content(version2, [0, 1, 0, 1, 1])
        verify_content_sets(version2, [1, 1, 0, 1, 1], [0, 1, 0, 1, 0], [0, 0, 1, 0, 0])

        # step 3
        remove_content(version2, [0, 0, 0, 1, 1])
        verify_content_sets(version2, [1, 1, 0, 0, 0], [0, 1, 0, 0, 0], [0, 0, 1, 0, 1])

        # step 4
        add_content(version2, [0, 0, 0, 1, 0])
        verify_content_sets(version2, [1, 1, 0, 1, 0], [0, 1, 0, 1, 0], [0, 0, 1, 0, 1])

    # Verify content sets after saving
    verify_content_sets(version1, [1, 0, 1, 0, 1], [1, 0, 1, 0, 1], [0, 0, 0, 0, 0])
    verify_content_sets(version2, [1, 1, 0, 1, 0], [0, 1, 0, 1, 0], [0, 0, 1, 0, 1])


def test_content_batch_qs(repository, content_pks, add_content):
    """Verify content iteration using content_batch_qs()."""
    sorted_pks = content_pks[:4]
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 0])  # v1 == four content units 0-3

        # Verify content_batch_qs on incomplete version
        qs_generator = version1.content_batch_qs(batch_size=2)
        assert pks_of_next_qs(qs_generator) == sorted_pks[:2]
        assert pks_of_next_qs(qs_generator) == sorted_pks[2:]
        with pytest.raises(StopIteration):
            pks_of_next_qs(qs_generator)

    # Verify on complete version
    # The last batch has only a single element (Depending on how a qs is
    # written, Django ORM sometimes returns the actual object instead of a
    # qs. This must not happen for the generator).
    reverse_pks = list(reversed(sorted_pks))
    qs_generator = version1.content_batch_qs(order_by_params=("-pk",), batch_size=3)
    assert pks_of_next_qs(qs_generator) == reverse_pks[:3]
    assert pks_of_next_qs(qs_generator) == reverse_pks[3:]
    with pytest.raises(StopIteration):
        pks_of_next_qs(qs_generator)


def test_content_batch_qs_using_filter(repository, content_pks, add_content):
    """Verify that a plugin can define a filtering query set for content_batch_qs()."""
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 0])  # v1 == four content units 0-3

    # Filter for pks 0-2 and 4 (4 is not part of the repo version, i.e.
    # must not be part of the content iterated over).
    pre_filter_qs = Content.objects.filter(pk__in=compress(content_pks, [1, 1, 1, 0, 1]))

    sorted_pks = content_pks[:3]
    qs_generator = version1.content_batch_qs(content_qs=pre_filter_qs, batch_size=2)
    assert pks_of_next_qs(qs_generator) == sorted_pks[:2]
    assert pks_of_next_qs(qs_generator) == sorted_pks[2:]
    with pytest.raises(StopIteration):
        pks_of_next_qs(qs_generator)


@pytest.mark.django_db
def test_next_version_with_one_version():
    repository = Repository.objects.create()
    repository.CONTENT_TYPES = [Content]

    assert repository.next_version == 1
    assert repository.latest_version().number == 0
    content = Content.objects.create(pulp_type="core.content")

    with repository.new_version() as version:
        version.add_content(Content.objects.filter(pk=content.pk))

    assert repository.next_version == 2
    assert repository.latest_version().number == 1

    version.delete()

    assert repository.next_version == 2
    assert repository.latest_version().number == 0


@pytest.mark.django_db
def test_next_version_with_multiple_versions():
    repository = Repository.objects.create()
    repository.CONTENT_TYPES = [Content]

    assert repository.next_version == 1
    assert repository.latest_version().number == 0

    contents = [Content(pulp_type="core.content") for _ in range(0, 3)]
    Content.objects.bulk_create(contents)

    versions = [repository.latest_version()]
    for content in contents:
        with repository.new_version() as version:
            version.add_content(Content.objects.filter(pk=content.pk))
            versions.append(version)

    assert repository.next_version == 4
    assert repository.latest_version().number == 3

    versions[2].delete()
    versions[3].delete()

    assert repository.next_version == 4
    assert repository.latest_version().number == 1
