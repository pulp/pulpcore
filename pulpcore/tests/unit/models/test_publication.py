from django.test import TestCase
from pulpcore.plugin.exceptions import UnsupportedDigestValidationError
from pulpcore.plugin.models import (
    Content,
    ContentArtifact,
    CreatedResource,
    Publication,
    Remote,
    RemoteArtifact,
    Repository,
)
from mock import patch


class PublicationTestCase(TestCase):
    def setUp(self):
        self.repository = Repository.objects.create()
        self.repository.CONTENT_TYPES = [Content]
        self.repository.save()
        self.remote = Remote.objects.create()
        self.remote.url = "www.pulpproject.org"
        self.remote.name = "testremote"
        self.remote.save()
        self.secondremote = Remote.objects.create()
        self.secondremote.url = "example.pulpproject.org"
        self.secondremote.name = "exampleremote"
        self.secondremote.save()

    @patch.object(CreatedResource, "save")
    def test_publication_create_all_remoteartifact_supported_checksum_type(self, save):
        save.return_value = True
        contents = []
        cntartifact = []
        for _ in range(2):
            cnt = Content.objects.create(pulp_type="core.content")
            ca = ContentArtifact.objects.create(content=cnt)
            contents.append(cnt)
            cntartifact.append(ca)

        for ca in cntartifact:
            RemoteArtifact.objects.create(
                url="http://example.pulpproject.org/ra",
                remote=self.remote,
                content_artifact=ca,
                sha256="3dfe13d3b8264db6bc66391af110b9fe932e0b9d170d160fbd81b9a5cdfd3040",
            )

        with self.repository.new_version() as version:
            version.add_content(Content.objects.filter(pk__in=[c.pk for c in contents]))

        publication = Publication.create(version)

        self.assertTrue(publication.pk)
        self.assertEqual(len(Publication.objects.all()), 1)

    @patch.object(CreatedResource, "save")
    def test_publication_create_one_remoteartifact_supported_checksum_type(self, save):
        save.return_value = True
        cnt = Content.objects.create(pulp_type="core.content")
        ca = ContentArtifact.objects.create(content=cnt)

        RemoteArtifact.objects.create(
            url="http://example.pulpproject.org/ra",
            remote=self.remote,
            content_artifact=ca,
            md5="e821ba1edb9dc0a445b61d8ce702052a",
        )
        RemoteArtifact.objects.create(
            url="http://example.pulpproject.org/ra",
            remote=self.secondremote,
            content_artifact=ca,
            sha256="3dfe13d3b8264db6bc66391af110b9fe932e0b9d170d160fbd81b9a5cdfd3040",
        )

        with self.repository.new_version() as version:
            version.add_content(Content.objects.filter(pk=cnt.pk))

        publication = Publication.create(version)

        self.assertTrue(publication.pk)
        self.assertEqual(len(Publication.objects.all()), 1)

    @patch.object(CreatedResource, "save")
    def test_publication_create_any_remoteartifact_supported_checksum_type(self, save):
        save.return_value = True
        cnt = Content.objects.create(pulp_type="core.content")
        ca = ContentArtifact.objects.create(content=cnt)

        RemoteArtifact.objects.create(
            url="http://example.pulpproject.org/ra",
            remote=self.remote,
            content_artifact=ca,
            md5="e821ba1edb9dc0a445b61d8ce702052a",
        )
        RemoteArtifact.objects.create(
            url="http://example.pulpproject.org/ra",
            remote=self.secondremote,
            content_artifact=ca,
            md5="e821ba1edb9dc0a445b61d8ce702052b",
        )

        with self.repository.new_version() as version:
            version.add_content(Content.objects.filter(pk=cnt.pk))

        with self.assertRaises(UnsupportedDigestValidationError):
            Publication.create(version)

        self.assertFalse(Publication.objects.all())
