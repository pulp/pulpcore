from uuid import uuid4

from django.conf import settings
from django.test import TestCase
from rest_framework.serializers import ValidationError as DRFValidationError

from pulp_file.app import models, viewsets

API_ROOT = (
    settings.V3_API_ROOT
    if not settings.DOMAIN_ENABLED
    else settings.V3_DOMAIN_API_ROOT.replace("<slug:pulp_domain>", "default")
)


class TestGetResource(TestCase):
    """
    Test NamedViewSet from core using some detail endpoints provided by file.

    Note: This is really a pulpcore test, but we can't test it from pulpcore.
    """

    def test_no_errors(self):
        """
        Tests that get_resource() properly resolves a valid URI and returns the correct resource.
        """

        repo = models.FileRepository.objects.create(name="foo")
        viewset = viewsets.FileRepositoryViewSet()
        resource = viewset.get_resource(
            "{api_root}repositories/file/file/{pk}/".format(api_root=API_ROOT, pk=repo.pk),
            models.FileRepository,
        )
        self.assertEquals(repo, resource)

    def test_multiple_matches(self):
        """
        Tests that get_resource() raises a ValidationError if you attempt to use a list endpoint.
        """
        models.FileRepository.objects.create(name="foo")
        models.FileRepository.objects.create(name="foo2")
        viewset = viewsets.FileRepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            # matches all repositories
            viewset.get_resource(
                "{api_root}repositories/file/file/".format(api_root=API_ROOT),
                models.FileRepository,
            )

    def test_invalid_uri(self):
        """
        Tests that get_resource raises a ValidationError if you attempt to use an invalid URI.
        """
        viewset = viewsets.FileRepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            viewset.get_resource("/pulp/api/v2/nonexistent/", models.FileRepository)

    def test_resource_does_not_exist(self):
        """
        Tests that get_resource() raises a ValidationError if you use a URI for a resource that
        does not exist.
        """
        pk = uuid4()
        viewset = viewsets.FileRepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            viewset.get_resource(
                "{api_root}repositories/file/file/{pk}/".format(api_root=API_ROOT, pk=pk),
                models.FileRepository,
            )

    def test_resource_with_field_error(self):
        """
        Tests that get_resource() raises a ValidationError if you use a URI that is not a valid
        model.
        """
        repo = models.FileRepository.objects.create(name="foo")
        viewset = viewsets.FileRepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            # has no repo versions yet
            viewset.get_resource(
                "{api_root}repositories/file/file/{pk}/versions/1/".format(
                    api_root=API_ROOT, pk=repo.pk
                ),
                models.FileRepository,
            )
