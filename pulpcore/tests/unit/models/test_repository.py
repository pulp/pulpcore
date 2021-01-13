from itertools import compress
from uuid import uuid4

from django.test import TestCase
from pulpcore.plugin.models import Content, Label, Repository, RepositoryVersion


class RepositoryVersionTestCase(TestCase):
    def setUp(self):
        self.repository = Repository.objects.create()
        self.repository.CONTENT_TYPES = [Content]
        self.repository.save()

        contents = []
        for _ in range(0, 5):
            contents.append(Content(pulp_type="core.content"))

        Content.objects.bulk_create(contents)
        self.pks = [c.pk for c in contents]

    def test_add_and_remove_content(self):
        contents = Content.objects.filter(pk__in=self.pks[:4])
        with self.repository.new_version() as version1:
            version1.add_content(contents)  # v1 == four content units 0-3

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

        added_pks_0 = version3.added(version0).values_list("pk", flat=True)
        removed_pks_0 = version3.removed(version0).values_list("pk", flat=True)

        self.assertCountEqual(added_pks_0, compress(self.pks, [1, 0, 1, 1]), added_pks_0)
        self.assertCountEqual(removed_pks_0, compress(self.pks, [0, 0, 0, 0]), removed_pks_0)

        added_pks_1 = version3.added(version1).values_list("pk", flat=True)
        removed_pks_1 = version3.removed(version1).values_list("pk", flat=True)

        self.assertCountEqual(added_pks_1, compress(self.pks, [0, 0, 0, 0]), added_pks_1)
        self.assertCountEqual(removed_pks_1, compress(self.pks, [0, 1, 0, 0]), removed_pks_1)

        added_pks_2 = version3.added(version2).values_list("pk", flat=True)
        removed_pks_2 = version3.removed(version2).values_list("pk", flat=True)

        self.assertCountEqual(added_pks_2, compress(self.pks, [1, 0, 0, 0]), added_pks_2)
        self.assertCountEqual(removed_pks_2, compress(self.pks, [0, 0, 0, 0]), removed_pks_2)

    def content_qs(self, pks):
        return Content.objects.filter(pk__in=pks)

    def verify_content_sets(self, version, content, added, removed):
        """
        Verify the content, added, and removed sets for a repository version.

        Args:
            version (pulpcore.app.models.RepositoryVersion): the version instance to verify
            content (list): "presence list" for content with respect to `self.pks`.
                For example, [1, 0, 1] means that content with self.pks[0], and
                self.pks[2] must be present, all other content must not be present.
            added (list): "presence list" for added content
            remove (list): "presence list" for removed content

        """
        content_pks = version.content.values_list("pk", flat=True)
        added_pks = version.added().values_list("pk", flat=True)
        removed_pks = version.removed().values_list("pk", flat=True)

        # There must never be content shown as added & removed
        self.assertSetEqual(set(added_pks).intersection(removed_pks), set())

        self.assertCountEqual(content_pks, compress(self.pks, content), content_pks)
        self.assertCountEqual(added_pks, compress(self.pks, added), added_pks)
        self.assertCountEqual(removed_pks, compress(self.pks, removed), removed_pks)

    def test_add_remove(self):
        """Verify that adding and then removing content units is handled properly."""
        latest_version = self.repository.latest_version()

        with self.repository.new_version() as version1:
            version1.add_content(self.content_qs(self.pks[:5]))
            self.verify_content_sets(version1, content=[1] * 5, added=[1] * 5, removed=[])

            version1.remove_content(self.content_qs(self.pks[:5]))
            self.verify_content_sets(version1, content=[], added=[], removed=[])

        self.assertEqual(
            self.repository.latest_version(), latest_version, msg="Empty version1 must not exist."
        )

    def test_remove_add(self):
        """Verify that removing and then adding content units is handled properly."""
        with self.repository.new_version() as version1:
            version1.add_content(self.content_qs(self.pks[:5]))  # v1 == content ids 0-4

        with self.repository.new_version() as version2:
            version2.remove_content(self.content_qs(self.pks[:5]))
            self.verify_content_sets(version2, content=[], added=[], removed=[1] * 5)

            version2.add_content(self.content_qs(self.pks[:5]))
            self.verify_content_sets(version2, content=[1] * 5, added=[], removed=[])

        self.assertEqual(
            self.repository.latest_version(), version1, msg="Empty version2 must not exist."
        )

    def test_multiple_adds_and_removes(self):
        """Verify that adding/removing content multiple times is handled properly.

        Additionally, verify that other content (untouched, simple add, simple
        remove) is not influenced and behaves as expected.
        """
        # v1 == content id 0, 2, and 4
        with self.repository.new_version() as version1:
            version1.add_content(self.content_qs([self.pks[0], self.pks[2], self.pks[4]]))

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
        with self.repository.new_version() as version2:
            # Content must be that of version1:
            self.verify_content_sets(version2, content=[1, 0, 1, 0, 1], added=[], removed=[])

            # step 1
            version2.remove_content(self.content_qs([self.pks[2], self.pks[4]]))
            self.verify_content_sets(
                version2, content=[1, 0, 0, 0, 0], added=[], removed=[0, 0, 1, 0, 1]
            )

            # step 2
            version2.add_content(self.content_qs([self.pks[1], self.pks[3], self.pks[4]]))

            self.verify_content_sets(
                version2, content=[1, 1, 0, 1, 1], added=[0, 1, 0, 1, 0], removed=[0, 0, 1, 0, 0]
            )

            # step 3
            version2.remove_content(self.content_qs([self.pks[3], self.pks[4]]))

            self.verify_content_sets(
                version2, content=[1, 1, 0, 0, 0], added=[0, 1, 0, 0, 0], removed=[0, 0, 1, 0, 1]
            )

            # step 4
            version2.add_content(self.content_qs([self.pks[3]]))

            self.verify_content_sets(
                version2, content=[1, 1, 0, 1, 0], added=[0, 1, 0, 1, 0], removed=[0, 0, 1, 0, 1]
            )

        # Verify content sets after saving
        self.verify_content_sets(
            version1, content=[1, 0, 1, 0, 1, 0], added=[1, 0, 1, 0, 1, 0], removed=[]
        )
        self.verify_content_sets(
            version2, content=[1, 1, 0, 1, 0], added=[0, 1, 0, 1, 0], removed=[0, 0, 1, 0, 1]
        )

    @staticmethod
    def pks_of_next_qs(qs_generator):
        """Iterate qs_generator one step and return the list of pks in the qs."""
        return list(next(qs_generator).values_list("pk", flat=True))

    def test_content_batch_qs(self):
        """Verify content iteration using content_batch_qs()."""
        sorted_pks = sorted(self.pks[:4])
        contents = Content.objects.filter(pk__in=self.pks[:4])
        with self.repository.new_version() as version1:
            version1.add_content(contents)  # v1 == four content units 0-3

            # Verify content_batch_qs on incomplete version
            qs_generator = version1.content_batch_qs(batch_size=2)
            self.assertListEqual(self.pks_of_next_qs(qs_generator), sorted_pks[:2])
            self.assertListEqual(self.pks_of_next_qs(qs_generator), sorted_pks[2:])
            with self.assertRaises(StopIteration):
                self.pks_of_next_qs(qs_generator)

        # Verify on complete version
        # The last batch has only a single element (Depending on how a qs is
        # written, Django ORM sometimes returns the actual object instead of a
        # qs. This must not happen for the generator).
        reverse_pks = sorted(self.pks[:4], reverse=True)
        qs_generator = version1.content_batch_qs(order_by_params=("-pk",), batch_size=3)
        self.assertListEqual(self.pks_of_next_qs(qs_generator), reverse_pks[:3])
        self.assertListEqual(self.pks_of_next_qs(qs_generator), reverse_pks[3:])
        with self.assertRaises(StopIteration):
            self.pks_of_next_qs(qs_generator)

    def test_content_batch_qs_using_filter(self):
        """Verify that a plugin can define a filtering query set for content_batch_qs()."""
        contents = Content.objects.filter(pk__in=self.pks[:4])
        with self.repository.new_version() as version1:
            version1.add_content(contents)  # v1 == four content units 0-3

        # Filter for pks 0-2 and 4 (4 is not part of the repo version, i.e.
        # must not be part of the content iterated over).
        pre_filter_qs = Content.objects.filter(pk__in=self.pks[:3] + [self.pks[4]])

        sorted_pks = sorted(self.pks[:3])
        qs_generator = version1.content_batch_qs(content_qs=pre_filter_qs, batch_size=2)
        self.assertListEqual(self.pks_of_next_qs(qs_generator), sorted_pks[:2])
        self.assertListEqual(self.pks_of_next_qs(qs_generator), sorted_pks[2:])
        with self.assertRaises(StopIteration):
            self.pks_of_next_qs(qs_generator)


class RepositoryTestCase(TestCase):
    def setUp(self):
        self.repository = Repository.objects.create()
        self.repository.CONTENT_TYPES = [Content]
        self.repository.save()

    def test_next_version_with_one_version(self):
        self.assertEqual(self.repository.next_version, 1, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 0, self.repository.latest_version().number
        )
        content = Content(pulp_type="core.content")
        content.save()

        with self.repository.new_version() as version:
            version.add_content(Content.objects.filter(pk=content.pk))

        self.assertEqual(self.repository.next_version, 2, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 1, self.repository.latest_version().number
        )

        version.delete()

        self.assertEqual(self.repository.next_version, 2, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 0, self.repository.latest_version().number
        )

    def test_next_version_with_multiple_versions(self):
        self.assertEqual(self.repository.next_version, 1, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 0, self.repository.latest_version().number
        )
        contents = []
        for _ in range(0, 3):
            contents.append(Content(pulp_type="core.content"))

        Content.objects.bulk_create(contents)

        versions = [self.repository.latest_version()]
        for content in contents:
            with self.repository.new_version() as version:
                version.add_content(Content.objects.filter(pk=content.pk))
                versions.append(version)

        self.assertEqual(self.repository.next_version, 4, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 3, self.repository.latest_version().number
        )

        versions[2].delete()
        versions[3].delete()

        self.assertEqual(self.repository.next_version, 4, self.repository.next_version)
        self.assertEqual(
            self.repository.latest_version().number, 1, self.repository.latest_version().number
        )

    def test_label_cascade(self):
        """Check that a repo's labels are deleted when it's deleted."""
        repo = Repository.objects.create(name=uuid4())
        repo.CONTENT_TYPES = [Content]
        repo.save()

        label = repo.pulp_labels.create(key="brown", value="radagast")
        self.assertTrue(Label.objects.filter(pk=label.pk).exists())
        repo.delete()
        self.assertFalse(Label.objects.filter(pk=label.pk).exists())
