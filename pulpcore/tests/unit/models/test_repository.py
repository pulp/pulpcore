from itertools import compress

from django.test import TestCase
from pulpcore.plugin.models import Content, Repository, RepositoryVersion


class RepositoryVersionTestCase(TestCase):

    def setUp(self):
        self.repository = Repository.objects.create()
        self.repository.CONTENT_TYPES = [Content]
        self.repository.save()

        contents = []
        for _ in range(0, 4):
            contents.append(Content(pulp_type="core.content"))

        Content.objects.bulk_create(contents)
        self.pks = [c.pk for c in contents]

    def test_add_and_remove_content(self):
        contents = Content.objects.filter(pk__in=self.pks)
        with self.repository.new_version() as version1:
            version1.add_content(contents)  # v1 == all contents

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
