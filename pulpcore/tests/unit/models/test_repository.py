import pytest
from uuid import uuid4

from itertools import compress

from pulpcore.app.models import RepositoryVersionContentDetails
from pulpcore.plugin.models import Artifact, Content, ContentArtifact, Repository
from pulpcore.plugin.repo_version_utils import validate_version_paths


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
        # assert that the memoization is set
        assert version.content_ids is not None
        # assert that content_ids list matches the RepositoryContent representation
        repo_content_pks = set(
            version._content_relationships().values_list("content_id", flat=True)
        )
        content_ids = set(version.content_ids)
        assert repo_content_pks == content_ids

        current_pks = set(version.content.values_list("pk", flat=True))
        added_pks = set(version.added(base_version).values_list("pk", flat=True))
        removed_pks = set(version.removed(base_version).values_list("pk", flat=True))

        # assert that the memoized content counts (distinct from content sets) are correct
        # NOTE: RepositoryVersionContentDetails stores counts for what was added/removed
        # BY this version (i.e., added()/removed() with base_version=None), not relative
        # to an arbitrary base_version. So we only verify RVCD when base_version is None.

        rvcd_qs = RepositoryVersionContentDetails.objects.filter(
            repository_version=version, content_type="core.content"
        )

        if rvcd_present := rvcd_qs.filter(
            count_type=RepositoryVersionContentDetails.PRESENT
        ).first():
            assert rvcd_present.count == len(current_pks)

        if base_version is None:
            if rvcd_added := rvcd_qs.filter(
                count_type=RepositoryVersionContentDetails.ADDED
            ).first():
                assert rvcd_added.count == len(added_pks)

            if rvcd_removed := rvcd_qs.filter(
                count_type=RepositoryVersionContentDetails.REMOVED
            ).first():
                assert rvcd_removed.count == len(removed_pks)

        # There must never be content shown as added & removed
        assert added_pks.intersection(removed_pks) == set()

        assert current_pks == set(compress(content_pks, current))
        assert added_pks == set(compress(content_pks, added))
        assert removed_pks == set(compress(content_pks, removed))

    return _verify_content_sets


def test_add_and_remove_content(db, repository, add_content, remove_content, verify_content_sets):
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


def test_add_remove(db, repository, add_content, remove_content, verify_content_sets):
    """Verify that adding and then removing content units is handled properly."""
    version0 = repository.latest_version()

    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 1])
        verify_content_sets(version1, [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [0, 0, 0, 0, 0])

        remove_content(version1, [1, 1, 1, 1, 1])
        verify_content_sets(version1, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0])

    assert repository.latest_version() == version0, "Empty version1 must not exist."


def test_remove_add(db, repository, add_content, remove_content, verify_content_sets):
    """Verify that removing and then adding content units is handled properly."""
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 1, 1])

    with repository.new_version() as version2:
        remove_content(version2, [1, 1, 1, 1, 1])
        verify_content_sets(version2, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 1, 1, 1])

        add_content(version2, [1, 1, 1, 1, 1])
        verify_content_sets(version2, [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0])

    assert repository.latest_version() == version1, "Empty version2 must not exist."


def test_multiple_adds_and_removes(
    db, repository, add_content, remove_content, verify_content_sets
):
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


def test_content_batch_qs(db, repository, content_pks, add_content):
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


def test_next_version_with_one_version(db, repository):
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


def test_next_version_with_multiple_versions(db, repository, content_pks):
    assert repository.next_version == 1
    assert repository.latest_version().number == 0

    versions = [repository.latest_version()]
    for pk in content_pks[:3]:
        with repository.new_version() as version:
            version.add_content(Content.objects.filter(pk=pk))
            versions.append(version)

    assert repository.next_version == 4
    assert repository.latest_version().number == 3

    versions[2].delete()
    versions[3].delete()

    assert repository.next_version == 4
    assert repository.latest_version().number == 1


def test_add_existing_content(db, repository, add_content, verify_content_sets):
    """Verify that adding content that already exists in the repo is a no-op."""
    version0 = repository.latest_version()

    # Create version1 with some content
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Try to add content that's already present (plus some new content)
    with repository.new_version() as version2:
        # Add content that's already in version1 (0, 1) and new content (3, 4)
        add_content(version2, [1, 1, 0, 1, 1])

    # Verify that version2 has the union of content, but only shows new content as "added"
    verify_content_sets(version1, [1, 1, 1, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0], version0)
    verify_content_sets(version2, [1, 1, 1, 1, 1], [0, 0, 0, 1, 1], [0, 0, 0, 0, 0], version1)
    verify_content_sets(version2, [1, 1, 1, 1, 1], [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], version0)


def test_remove_absent_content(db, repository, add_content, remove_content, verify_content_sets):
    """Verify that removing content that doesn't exist in the repo is a no-op."""
    version0 = repository.latest_version()

    # Create version1 with some content
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Try to remove content that's not present (3, 4) along with content that is (0, 1)
    with repository.new_version() as version2:
        remove_content(version2, [1, 1, 0, 1, 1])

    # Verify that only content that was actually present is shown as "removed"
    verify_content_sets(version2, [0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0], version1)
    verify_content_sets(version2, [0, 0, 1, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 0, 0], version0)


def test_empty_version_no_operations(repository):
    """Verify that creating a version with no operations doesn't create a new version."""
    version0 = repository.latest_version()

    # Open and close a version context without doing anything
    with repository.new_version():
        pass

    # No new version should be created
    assert repository.latest_version() == version0, "Empty version must not be created."


def test_version_identical_to_previous(repository, add_content, remove_content):
    """Verify that a version identical to the previous version is not created."""
    # Create version1 with some content
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Create a version that adds and removes content, ending up identical to version1
    with repository.new_version() as version2:
        add_content(version2, [0, 0, 0, 1, 1])  # Add content 3, 4
        remove_content(version2, [0, 0, 0, 1, 1])  # Remove content 3, 4

    # Version2 should not be created since it's identical to version1
    assert repository.latest_version() == version1, "Identical version must not be created."

    # Create a version that removes and then adds content, ending up identical to version1
    with repository.new_version() as version3:
        remove_content(version3, [1, 1, 0, 0, 0])  # Remove content 3, 4
        add_content(version3, [1, 1, 0, 0, 0])  # Add content 3, 4

    # Version3 should not be created since it's identical to version1
    assert repository.latest_version() == version1, "Identical version must not be created."


def test_base_version_none(db, repository, add_content, verify_content_sets):
    """Verify that added() and removed() work correctly when base_version is None."""
    # When base_version is None, added() should return all content, removed() should be empty
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Explicitly pass None as base_version
    verify_content_sets(
        version1, [1, 1, 1, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0], base_version=None
    )


def test_non_sequential_version_comparison(
    repository, add_content, remove_content, verify_content_sets
):
    """Verify that comparing non-sequential versions works correctly."""
    version0 = repository.latest_version()

    # Create version1 with content 0, 1, 2
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Create version2 that removes content 0
    with repository.new_version() as version2:
        remove_content(version2, [1, 0, 0, 0, 0])

    # Create version3 that adds content 3
    with repository.new_version() as version3:
        add_content(version3, [0, 0, 0, 1, 0])

    # Create version4 that adds content 4 and removes content 1
    with repository.new_version() as version4:
        add_content(version4, [0, 0, 0, 0, 1])
        remove_content(version4, [0, 1, 0, 0, 0])

    # Compare version4 to version1 (skipping version2 and version3)
    # version1: [1, 1, 1, 0, 0]
    # version4: [0, 0, 1, 1, 1]
    # added: 3, 4
    # removed: 0, 1
    verify_content_sets(version4, [0, 0, 1, 1, 1], [0, 0, 0, 1, 1], [1, 1, 0, 0, 0], version1)

    # Compare version4 to version0 (skipping all intermediate versions)
    verify_content_sets(version4, [0, 0, 1, 1, 1], [0, 0, 1, 1, 1], [0, 0, 0, 0, 0], version0)


def test_version_compared_to_itself(repository, add_content, verify_content_sets):
    """Verify that comparing a version to itself shows no additions or removals."""
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Compare version1 to itself
    verify_content_sets(version1, [1, 1, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], version1)


def test_add_empty_queryset(db, repository):
    """Verify that adding an empty queryset doesn't create a version."""
    version0 = repository.latest_version()

    # Add empty queryset
    with repository.new_version() as version1:
        version1.add_content(Content.objects.none())

    # No version should be created
    assert repository.latest_version() == version0


def test_add_nonexistent_content(db, repository):
    """Verify that attempting to add non-existent content is handled correctly."""
    # Create a content unit
    content = Content.objects.create(pulp_type="core.content")

    # Create version with existing content
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk=content.pk))

    assert version1.content.count() == 1

    # Try to add content using a non-existent PK (empty queryset)
    with repository.new_version() as version2:
        # This should not fail, just add nothing (empty queryset)
        version2.add_content(Content.objects.filter(pk=uuid4()))

    # Version2 should not be created since no content was actually added
    assert repository.latest_version() == version1


def test_add_wrong_content_type(db, repository):
    """Verify that adding content of wrong type is handled."""
    # Create content with a different pulp_type
    wrong_type_content = Content.objects.create(pulp_type="wrong.type")
    correct_type_content = Content.objects.create(pulp_type="core.content")

    # Creating a repository version containing a type disallowed by the repository
    # should raise an error
    with pytest.raises(ValueError):
        with repository.new_version() as version1:
            version1.add_content(Content.objects.filter(pk=wrong_type_content.pk))
            version1.add_content(Content.objects.filter(pk=correct_type_content.pk))


def test_add_remove_non_content_type(db, repository):
    """Verify that adding a queryset of non-Content type raises AssertionError."""
    # Create a real Content object first
    content = Content.objects.create(pulp_type="core.content")

    # Create a ContentArtifact which is NOT a Content subclass
    content_artifact = ContentArtifact.objects.create(content=content, relative_path="test/path")

    # Attempting to add a queryset of ContentArtifact (not Content) should raise AssertionError
    with pytest.raises(AssertionError):
        with repository.new_version() as version1:
            version1.add_content(ContentArtifact.objects.filter(pk=content_artifact.pk))

    # Attempting to add a queryset of ContentArtifact (not Content) should raise AssertionError
    with pytest.raises(AssertionError):
        with repository.new_version() as version1:
            version1.remove_content(ContentArtifact.objects.filter(pk=content_artifact.pk))


def test_remove_empty_queryset(db, repository):
    """Verify that removing an empty queryset doesn't create a version."""
    content = Content.objects.create(pulp_type="core.content")

    # Create version with content
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk=content.pk))

    # Remove empty queryset
    with repository.new_version() as version2:
        version2.remove_content(Content.objects.none())

    # No new version should be created
    assert repository.latest_version() == version1


def test_remove_nonexistent_content_from_version(db, repository):
    """Verify that removing non-existent content doesn't cause errors."""
    contents = [Content(pulp_type="core.content") for _ in range(3)]
    Content.objects.bulk_create(contents)
    pks = [c.pk for c in contents]

    # Create version with some content
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk__in=pks[:2]))

    # Try to remove content that was never in the repository
    with repository.new_version() as version2:
        # This should not fail, just remove nothing
        version2.remove_content(Content.objects.filter(pk=pks[2]))

    # Version2 should not be created since nothing changed
    assert repository.latest_version() == version1


def test_mixed_add_remove_with_empty_result(db, repository, content_pks):
    """Verify that mixed operations resulting in no change don't create a version."""
    # Create version with content
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk__in=content_pks))

    # Perform operations that cancel out
    with repository.new_version() as version2:
        # Remove content that doesn't exist (no-op)
        version2.remove_content(Content.objects.filter(pk=9999999))
        # Add content that already exists (no-op)
        version2.add_content(Content.objects.filter(pk=content_pks[0]))

    # No new version should be created
    assert repository.latest_version() == version1


def test_operations_on_completed_version(db, repository, content_pks):
    """Verify that operations on a completed version are not allowed."""
    # Create and complete a version
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk=content_pks[0]))

    # Version is now complete. Trying to modify it should fail
    # The version context manager sets the version as complete on exit
    with pytest.raises(Exception):  # Could be various exceptions depending on implementation
        version1.add_content(Content.objects.filter(pk=content_pks[1]))


def test_transaction_rollback_on_error(db, repository):
    """Verify that transaction rollback works correctly when version creation fails."""
    content = Content.objects.create(pulp_type="core.content")
    version0 = repository.latest_version()

    # Try to create a version but force an error
    try:
        with repository.new_version() as version1:
            version1.add_content(Content.objects.filter(pk=content.pk))
            # Force an error by raising an exception
            raise ValueError("Simulated error during version creation")
    except ValueError:
        pass

    # The version should not have been created due to rollback
    assert repository.latest_version() == version0
    # Repository should still be in a valid state
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk=content.pk))
    assert repository.latest_version().number == 1


def test_shared_artifact_same_path_validation(db, tmp_path, repository):
    """
    Test that multiple content units can reference the same artifact with the same
    relative path without causing validation errors.

    This reproduces scenarios where different content units legitimately share
    the same artifact (e.g. upstream source files).
    """
    # Create a shared artifact using proper test pattern
    artifact_path = tmp_path / "shared_file.txt"
    artifact_path.write_text("Shared content data")
    shared_artifact = Artifact.init_and_validate(str(artifact_path))
    shared_artifact.save()

    # Create two content units (simulates any content that shares artifacts)
    content1 = Content.objects.create(pulp_type="core.content")
    content2 = Content.objects.create(pulp_type="core.content")

    # Both content units reference the same artifact with same path
    ContentArtifact.objects.create(
        content=content1, artifact=shared_artifact, relative_path="shared/common_file.txt"
    )
    ContentArtifact.objects.create(
        content=content2, artifact=shared_artifact, relative_path="shared/common_file.txt"
    )

    # Create a repository version with both content units
    with repository.new_version() as new_version:
        new_version.add_content(Content.objects.filter(pk__in=[content1.pk, content2.pk]))

    # This should not raise validation errors with our fix
    validate_version_paths(new_version)


def test_different_artifacts_same_path_validation_fails(db, tmp_path, repository):
    """
    Test that different artifacts trying to use the same relative path
    still fail validation (this is a real conflict that should be caught).
    """
    # Create two different artifacts using proper test pattern
    artifact1_path = tmp_path / "artifact1.txt"
    artifact1_path.write_text("Content of first artifact")
    artifact1 = Artifact.init_and_validate(str(artifact1_path))
    artifact1.save()

    artifact2_path = tmp_path / "artifact2.txt"
    artifact2_path.write_text("Content of second artifact")  # Different content
    artifact2 = Artifact.init_and_validate(str(artifact2_path))
    artifact2.save()

    # Create two content units with different artifacts but same path
    content1 = Content.objects.create(pulp_type="core.content")
    content2 = Content.objects.create(pulp_type="core.content")

    ContentArtifact.objects.create(
        content=content1, artifact=artifact1, relative_path="conflicting/file.txt"
    )
    ContentArtifact.objects.create(
        content=content2,
        artifact=artifact2,
        relative_path="conflicting/file.txt",  # Same path, different artifact
    )

    # Create a repository version with both content units
    with repository.new_version() as new_version:
        new_version.add_content(Content.objects.filter(pk__in=[content1.pk, content2.pk]))

    # This should raise a validation error due to path conflict
    with pytest.raises(ValueError, match="Repository version errors"):
        validate_version_paths(new_version)


def test_content_relationships_after_version_deletion(
    repository, add_content, remove_content, verify_content_sets
):
    """Verify behavior when comparing to a deleted base version."""
    version0 = repository.latest_version()

    # Create version1 with content 0, 1, 2, 4
    with repository.new_version() as version1:
        add_content(version1, [1, 1, 1, 0, 0])

    # Create version2 that adds content 3 and removes content 2
    with repository.new_version() as version2:
        add_content(version2, [0, 0, 0, 0, 1])
        remove_content(version2, [0, 1, 0, 0, 0])

    # Create version3 that removes content
    with repository.new_version() as version3:
        remove_content(version3, [0, 0, 1, 0, 0])

    verify_content_sets(version2, [1, 0, 1, 0, 1], [0, 0, 0, 0, 1], [0, 1, 0, 0, 0])
    verify_content_sets(
        version2, [1, 0, 1, 0, 1], [1, 0, 1, 0, 1], [0, 0, 0, 0, 0], base_version=version0
    )
    verify_content_sets(version3, [1, 0, 0, 0, 1], [0, 0, 0, 0, 0], [0, 0, 1, 0, 0])

    # Delete version1
    version1.delete()

    verify_content_sets(version2, [1, 0, 1, 0, 1], [1, 0, 1, 0, 1], [0, 0, 0, 0, 0])
    verify_content_sets(version3, [1, 0, 0, 0, 1], [0, 0, 0, 0, 0], [0, 0, 1, 0, 0])

    # Verify that comparing to version0 still works
    added_pks = set(version2.added(base_version=version0).values_list("pk", flat=True))
    removed_pks = set(version2.removed(base_version=version0).values_list("pk", flat=True))
    assert len(added_pks) == 3
    assert len(removed_pks) == 0

    # Delete version2
    version2.delete()

    verify_content_sets(version3, [1, 0, 0, 0, 1], [1, 0, 0, 0, 1], [0, 0, 0, 0, 0])

    # Verify that comparing to version0 still works
    added_pks = set(version3.added(base_version=version0).values_list("pk", flat=True))
    removed_pks = set(version3.removed(base_version=version0).values_list("pk", flat=True))
    assert len(added_pks) == 2
    assert len(removed_pks) == 0


def test_comparing_distant_versions(repository, add_content, remove_content, verify_content_sets):
    """Verify comparing versions that are many versions apart."""
    version0 = repository.latest_version()

    # Create a chain of versions, each modifying content
    versions = [version0]

    # Version 1: Add content 0, 1
    with repository.new_version() as v:
        add_content(v, [1, 1, 0, 0, 0])
    versions.append(v)

    # Version 2: Add content 2
    with repository.new_version() as v:
        add_content(v, [0, 0, 1, 0, 0])
    versions.append(v)

    # Version 3: Remove content 0
    with repository.new_version() as v:
        remove_content(v, [1, 0, 0, 0, 0])
    versions.append(v)

    # Version 4: Add content 3
    with repository.new_version() as v:
        add_content(v, [0, 0, 0, 1, 0])
    versions.append(v)

    # Version 5: Remove content 1
    with repository.new_version() as v:
        remove_content(v, [0, 1, 0, 0, 0])
    versions.append(v)

    # Version 6: Add content 4
    with repository.new_version() as v:
        add_content(v, [0, 0, 0, 0, 1])
    versions.append(v)

    # Version 7: Add content 0 back
    with repository.new_version() as v:
        add_content(v, [1, 0, 0, 0, 0])
    versions.append(v)

    # Compare version 7 to version 1 (6 versions apart)
    # Version 1: [1, 1, 0, 0, 0]
    # Version 7: [1, 0, 1, 1, 1]
    # added: 2, 3, 4
    # removed: 1
    verify_content_sets(
        versions[7], [1, 0, 1, 1, 1], [0, 0, 1, 1, 1], [0, 1, 0, 0, 0], base_version=versions[1]
    )

    # Compare version 7 to version 0 (start)
    verify_content_sets(
        versions[7], [1, 0, 1, 1, 1], [1, 0, 1, 1, 1], [0, 0, 0, 0, 0], base_version=version0
    )


def test_batch_operations_preserve_correctness(repository, db):
    """Verify that batching content operations maintains correctness."""
    # Create content in batches
    batch1 = [Content(pulp_type="core.content") for _ in range(30)]
    batch2 = [Content(pulp_type="core.content") for _ in range(30)]
    batch3 = [Content(pulp_type="core.content") for _ in range(40)]

    Content.objects.bulk_create(batch1)
    Content.objects.bulk_create(batch2)
    Content.objects.bulk_create(batch3)

    batch1_pks = sorted([c.pk for c in batch1])
    batch2_pks = sorted([c.pk for c in batch2])
    batch3_pks = sorted([c.pk for c in batch3])

    # Add content in batches within a single version
    with repository.new_version() as version1:
        version1.add_content(Content.objects.filter(pk__in=batch1_pks))
        version1.add_content(Content.objects.filter(pk__in=batch2_pks))
        version1.add_content(Content.objects.filter(pk__in=batch3_pks))

    # Verify all content was added
    assert version1.content.count() == 100

    # Verify RepositoryVersionContentDetails
    rvcd_qs = RepositoryVersionContentDetails.objects.filter(
        repository_version=version1, content_type="core.content"
    )
    assert rvcd_qs.get(count_type=RepositoryVersionContentDetails.PRESENT).count == 100
    assert rvcd_qs.get(count_type=RepositoryVersionContentDetails.ADDED).count == 100
    assert rvcd_qs.filter(count_type=RepositoryVersionContentDetails.REMOVED).first() is None

    # Remove content in batches
    with repository.new_version() as version2:
        version2.remove_content(Content.objects.filter(pk__in=batch1_pks))
        version2.remove_content(Content.objects.filter(pk__in=batch2_pks))

    # Verify correct content remains
    assert version2.content.count() == 40

    # Verify RepositoryVersionContentDetails
    rvcd_qs = RepositoryVersionContentDetails.objects.filter(
        repository_version=version2, content_type="core.content"
    )
    assert rvcd_qs.get(count_type=RepositoryVersionContentDetails.PRESENT).count == 40
    assert rvcd_qs.filter(count_type=RepositoryVersionContentDetails.ADDED).first() is None
    assert rvcd_qs.get(count_type=RepositoryVersionContentDetails.REMOVED).count == 60
