from itertools import compress

from django.test import TransactionTestCase
from pulpcore.plugin.models import Content, Repository, RepositoryVersion


class RepositoryVersionTestCase(TransactionTestCase):

    def setUp(self):
        self.repository = Repository.objects.create()
        self.repository.CONTENT_TYPES = [Content]
        self.repository.save()

        contents = []
        for _ in range(0, 20):
            contents.append(Content(pulp_type="core.content"))

        Content.objects.bulk_create(contents)
        self.pks = [c.pk for c in contents]

    def test_add_and_remove_content(self):
        contents = Content.objects.filter(pk__in=self.pks[:4])
        with self.repository.new_version() as version1:
            version1.add_content(contents)  # v1 == four content units

        to_remove = contents[0:2]
        with self.repository.new_version() as version2:
            version2.remove_content(to_remove)  # v2 == removed 2 first contents

        to_add = Content.objects.filter(pk=contents[0].pk)
        with self.repository.new_version() as version3:
            version3.add_content(to_add)  # v3 == added first content

        version0 = RepositoryVersion.objects.filter(number=0, repository=self.repository).first()

        self.assertEqual(version0.added().count(), 0)
        self.assertEqual(version1.added().count(), 4)
        self.assertEqual(version2.added().count(), 0)
        self.assertEqual(version3.added().count(), 1)

        self.assertEqual(version0.removed().count(), 0)
        self.assertEqual(version1.removed().count(), 0)
        self.assertEqual(version2.removed().count(), 2)
        self.assertEqual(version3.removed().count(), 0)

        self.assertEqual(version3.added(version0).count(), 3)
        self.assertEqual(version3.removed(version0).count(), 0)

        added_pks_0 = version3.added(version0).values_list('pk', flat=True)
        removed_pks_0 = version3.removed(version0).values_list('pk', flat=True)

        self.assertCountEqual(added_pks_0, compress(self.pks, [1, 0, 1, 1]), added_pks_0)
        self.assertCountEqual(removed_pks_0, compress(self.pks, [0, 0, 0, 0]), removed_pks_0)

        added_pks_1 = version3.added(version1).values_list('pk', flat=True)
        removed_pks_1 = version3.removed(version1).values_list('pk', flat=True)

        self.assertCountEqual(added_pks_1, compress(self.pks, [0, 0, 0, 0]), added_pks_1)
        self.assertCountEqual(removed_pks_1, compress(self.pks, [0, 1, 0, 0]), removed_pks_1)

        added_pks_2 = version3.added(version2).values_list('pk', flat=True)
        removed_pks_2 = version3.removed(version2).values_list('pk', flat=True)

        self.assertCountEqual(added_pks_2, compress(self.pks, [1, 0, 0, 0]), added_pks_2)
        self.assertCountEqual(removed_pks_2, compress(self.pks, [0, 0, 0, 0]), removed_pks_2)

    def content_qs(self, pks):
        return Content.objects.filter(pk__in=pks)

    def verify_content_sets(self, version, content, added, removed):
        content_pks = version.content.values_list('pk', flat=True)
        added_pks = version.added().values_list('pk', flat=True)
        removed_pks = version.removed().values_list('pk', flat=True)

        self.assertCountEqual(content_pks, compress(self.pks, content), content_pks)
        self.assertCountEqual(added_pks, compress(self.pks, added), added_pks)
        self.assertCountEqual(removed_pks, compress(self.pks, removed), removed_pks)

    def test_normalize_repository_content(self):
        with self.repository.new_version() as version1:
            version1.add_content(self.content_qs(self.pks[:5]))  # v1 == content 0-4

        # v2 content:
        # 0 leave as is
        # 1 remove
        # 2 remove, re-add
        # 3 remove, re-add, remove
        # 4 remove, re-add, remove, re-add
        # 5 add
        # 6 add, remove
        # 7 add, remove, re-add
        # 8 add, remone, re-add, remove
        # Expected content: 0, 2, 4, 5, 7
        # Added: 5, 7
        # Removed: 1, 3
        with self.repository.new_version() as version2:  # v2 == content 0, 1 and 3
            self.verify_content_sets(version2, content=[1]*5, added=[], removed=[])

            version2.remove_content(self.content_qs(self.pks[1:5]))
            self.verify_content_sets(version2, content=[1], added=[], removed=[0, 1, 1, 1, 1])

            version2.add_content(self.content_qs(self.pks[2:5]))
            self.verify_content_sets(version2, content=[1, 0, 1, 1, 1], added=[], removed=[0, 1])

            version2.remove_content(self.content_qs(self.pks[3:5]))
            self.verify_content_sets(version2, content=[1, 0, 1], added=[], removed=[0, 1, 0, 1, 1])

            version2.add_content(self.content_qs(self.pks[4:5]))
            self.verify_content_sets(
                version2,
                content=[1, 0, 1, 0, 1],
                added=[],
                removed=[0, 1, 0, 1]
            )

            version2.add_content(self.content_qs(self.pks[5:9]))
            self.verify_content_sets(
                version2,
                content=[1, 0, 1, 0, 1, 1, 1, 1, 1],
                added=[0, 0, 0, 0, 0, 1, 1, 1, 1],
                removed=[0, 1, 0, 1],
            )

            version2.remove_content(self.content_qs(self.pks[6:9]))
            self.verify_content_sets(
                version2,
                content=[1, 0, 1, 0, 1, 1],
                added=[0, 0, 0, 0, 0, 1],
                removed=[0, 1, 0, 1],
            )

            version2.add_content(self.content_qs(self.pks[7:9]))
            self.verify_content_sets(
                version2,
                content=[1, 0, 1, 0, 1, 1, 0, 1, 1],
                added=[0, 0, 0, 0, 0, 1, 0, 1, 1],
                removed=[0, 1, 0, 1],
            )

            version2.remove_content(self.content_qs(self.pks[8:9]))
            self.verify_content_sets(
                version2,
                content=[1, 0, 1, 0, 1, 1, 0, 1],
                added=[0, 0, 0, 0, 0, 1, 0, 1],
                removed=[0, 1, 0, 1],
            )

        # Verify content sets after normalization
        self.verify_content_sets(version1, content=[1]*5, added=[1]*5, removed=[])
        self.verify_content_sets(
            version2,
            content=[1, 0, 1, 0, 1, 1, 0, 1],
            added=[0, 0, 0, 0, 0, 1, 0, 1],
            removed=[0, 1, 0, 1],
        )

    def normalize_repository_content_batches(self, batch_size):
        """Test helper for different batch sizes."""
        with self.repository.new_version() as version1:
            version1.add_content(self.content_qs(self.pks[:10]))  # v1 == content 0-9

        with self.repository.new_version() as version2:
            self.verify_content_sets(version2, content=[1]*10, added=[], removed=[])

            version2.add_content(self.content_qs(self.pks[10:20]))
            self.verify_content_sets(version2, content=[1]*20, added=[0]*10 + [1]*10, removed=[])

            version2.remove_content(self.content_qs(self.pks))
            self.verify_content_sets(version2, content=[], added=[], removed=[1]*10)

            version2.add_content(self.content_qs(self.pks[:10]))
            self.verify_content_sets(version2, content=[1]*10, added=[], removed=[])

            version2._normalize_repository_content(batch_size=batch_size)

            # After version is normalized, nothing must change
            self.verify_content_sets(version2, content=[1]*10, added=[], removed=[])

            # Normalization must get rid of all RepositoryContent records
            # that contain this version (as nothing has been added nor removed)
            self.assertEqual(
                version2._content_relationships().filter(version_added=version2).count(), 0
            )
            self.assertEqual(
                version2._content_relationships().filter(version_removed=version2).count(), 0
            )

    def test_normalize_repository_content_batches_size_1(self):
        """Verify smallest possible batch size."""
        self.normalize_repository_content_batches(batch_size=1)

    def test_normalize_repository_content_batches_size_2(self):
        """Verify number of content units is a multiple of batch size."""
        self.normalize_repository_content_batches(batch_size=2)

    def test_normalize_repository_content_batches_size_3(self):
        """Verify number of content units is no multiple of batch size."""
        self.normalize_repository_content_batches(batch_size=3)
