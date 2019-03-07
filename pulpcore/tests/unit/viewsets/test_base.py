import unittest

from django.http import Http404, QueryDict
from django.test import TestCase
from rest_framework.serializers import ValidationError as DRFValidationError
from uuid import uuid4

from pulpcore.app import models, viewsets, serializers
from pulpcore.constants import API_ROOT


class TestGetQuerySet(TestCase):
    @unittest.skip("fails for unknown reasons")
    def test_adds_filters(self):
        """
        Tests to make sure the correct lookup is being added to the queryset based on its
        'parent_lookup_kwargs' value.
        """
        repo = models.Repository.objects.create(name='foo')
        repo2 = models.Repository.objects.create(name='foo2')
        # no concurrency so this is fine
        models.RepositoryVersion.objects.create(repository=repo, number=1)
        models.RepositoryVersion.objects.create(repository=repo2, number=1)
        viewset = viewsets.RepositoryVersionViewSet()
        viewset.kwargs = {'repository_pk': repo.pk}
        queryset = viewset.get_queryset()
        expected = models.RepositoryVersion.objects.filter(repository__pk=repo.pk)

        # weird, stupid django quirk
        # https://docs.djangoproject.com/en/2.0/topics/testing/tools/#django.test.TransactionTestCase.assertQuerysetEqual
        self.assertQuerysetEqual(queryset, map(repr, expected))

    def test_does_not_add_filters(self):
        """
        Tests to make sure no filters are applied, based on its empty 'parent_lookup_kwargs'
        value.
        """
        models.Repository.objects.create(name='foo')
        viewset = viewsets.RepositoryViewSet()
        viewset.kwargs = {'name': 'foo'}
        queryset = viewset.get_queryset()
        expected = models.Repository.objects.all()

        # weird, stupid django quirk
        # https://docs.djangoproject.com/en/2.0/topics/testing/tools/#django.test.TransactionTestCase.assertQuerysetEqual
        self.assertQuerysetEqual(queryset, map(repr, expected))


class TestGetResource(TestCase):
    def test_no_errors(self):
        """
        Tests that get_resource() properly resolves a valid URI and returns the correct resource.
        """
        repo = models.Repository.objects.create(name='foo')
        viewset = viewsets.RepositoryViewSet()
        resource = viewset.get_resource(
            "/{api_root}repositories/{pk}/".format(api_root=API_ROOT, pk=repo.pk),
            models.Repository
        )
        self.assertEquals(repo, resource)

    def test_multiple_matches(self):
        """
        Tests that get_resource() raises a ValidationError if you attempt to use a list endpoint.
        """
        models.Repository.objects.create(name='foo')
        models.Repository.objects.create(name='foo2')
        viewset = viewsets.RepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            # matches all repositories
            viewset.get_resource("/{api_root}repositories/".format(api_root=API_ROOT),
                                 models.Repository)

    def test_invalid_uri(self):
        """
        Tests that get_resource raises a ValidationError if you attempt to use an invalid URI.
        """
        viewset = viewsets.RepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            viewset.get_resource("/pulp/api/v2/nonexistent/", models.Repository)

    def test_resource_does_not_exist(self):
        """
        Tests that get_resource() raises a ValidationError if you use a URI for a resource that
        does not exist.
        """
        pk = uuid4()
        viewset = viewsets.RepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            viewset.get_resource(
                "/{api_root}repositories/{pk}/".format(api_root=API_ROOT, pk=pk),
                models.Repository
            )

    def test_resource_with_field_error(self):
        """
        Tests that get_resource() raises a ValidationError if you use a URI that is not a valid
        model.
        """
        repo = models.Repository.objects.create(name='foo')
        viewset = viewsets.RepositoryViewSet()

        with self.assertRaises(DRFValidationError):
            # has no repo versions yet
            viewset.get_resource(
                "/{api_root}repositories/{pk}/versions/1/".format(api_root=API_ROOT, pk=repo.pk),
                models.Repository
            )


class TestGetSerializerClass(TestCase):

    def test_must_define_serializer_class(self):
        """
        Test that get_serializer_class() raises an AssertionError if you don't define the
        serializer_class attribute.
        """
        class TestTaskViewSet(viewsets.NamedModelViewSet):
            minimal_serializer_class = serializers.MinimalTaskSerializer

        with self.assertRaises(AssertionError):
            TestTaskViewSet().get_serializer_class()

    def test_serializer_class(self):
        """
        Tests that get_serializer_class() returns the serializer_class attribute if it exists,
        and that it doesn't error if no minimal serializer is defined, but minimal=True.
        """
        class TestTaskViewSet(viewsets.NamedModelViewSet):
            serializer_class = serializers.TaskSerializer

        viewset = TestTaskViewSet()
        self.assertEquals(viewset.get_serializer_class(), serializers.TaskSerializer)

        request = unittest.mock.MagicMock()
        request.query_params = QueryDict('minimal=True')
        viewset.request = request

        self.assertEquals(viewset.get_serializer_class(), serializers.TaskSerializer)

    def test_minimal_query_param(self):
        """
        Tests that get_serializer_class() returns the correct serializer in the correct situations.
        """
        class TestTaskViewSet(viewsets.NamedModelViewSet):
            serializer_class = serializers.TaskSerializer
            minimal_serializer_class = serializers.MinimalTaskSerializer

        viewset = TestTaskViewSet()
        request = unittest.mock.MagicMock()

        # Test that it uses the full serializer with no query params
        request.query_params = QueryDict()
        viewset.request = request
        self.assertEquals(viewset.get_serializer_class(), serializers.TaskSerializer)
        # Test that it uses the full serializer with minimal=False
        request.query_params = QueryDict('minimal=False')
        viewset.request = request
        self.assertEquals(viewset.get_serializer_class(), serializers.TaskSerializer)
        # Test that it uses the minimal serializer with minimal=True
        request.query_params = QueryDict('minimal=True')
        viewset.request = request
        self.assertEquals(viewset.get_serializer_class(), serializers.MinimalTaskSerializer)


class TestGetParentFieldAndObject(TestCase):
    def test_no_parent_object(self):
        """
        Tests that get_parent_field_and_object() raises django.http.Http404 if the parent object
        does not exist on a nested viewset.
        """
        viewset = viewsets.RepositoryVersionViewSet()
        viewset.kwargs = {'repository_pk': 500}

        with self.assertRaises(Http404):
            viewset.get_parent_field_and_object()

    def test_get_parent_field_and_object(self):
        """
        Tests that get_parent_field_and_object() returns the correct parent field and parent
        object.
        """
        repo = models.Repository.objects.create(name='foo')
        viewset = viewsets.RepositoryVersionViewSet()
        viewset.kwargs = {'repository_pk': repo.pk}

        self.assertEquals(('repository', repo), viewset.get_parent_field_and_object())

    def test_get_parent_object(self):
        """
        Tests that get_parent_object() returns the correct parent object.
        """
        repo = models.Repository.objects.create(name='foo')
        viewset = viewsets.RepositoryVersionViewSet()
        viewset.kwargs = {'repository_pk': repo.pk}

        self.assertEquals(repo, viewset.get_parent_object())


class TestGetNestDepth(TestCase):
    def test_get_nest_depth(self):
        """
        Test that _get_nest_depth() returns the correct nesting depths.
        """
        self.assertEquals(1, viewsets.RepositoryViewSet._get_nest_depth())
        self.assertEquals(2, viewsets.RepositoryVersionViewSet._get_nest_depth())
