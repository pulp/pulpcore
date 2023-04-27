import pytest
from pytest_django.asserts import assertQuerysetEqual
import unittest

from django.http import Http404, QueryDict

from pulpcore.app import models, serializers, viewsets


@pytest.mark.django_db
def test_adds_filters():
    """
    Tests to make sure the correct lookup is being added to the queryset based on its
    'parent_lookup_kwargs' value.
    """
    repo = models.Repository.objects.create(name="foo")
    repo2 = models.Repository.objects.create(name="foo2")
    # no concurrency so this is fine
    models.RepositoryVersion.objects.create(repository=repo, number=1, complete=True)
    models.RepositoryVersion.objects.create(repository=repo2, number=1, complete=True)
    viewset = viewsets.RepositoryVersionViewSet()
    viewset.kwargs = {"repository_pk": repo.pk}
    queryset = viewset.get_queryset()
    expected = models.RepositoryVersion.objects.filter(repository__pk=repo.pk)

    assertQuerysetEqual(queryset, expected)


@pytest.mark.django_db
def test_does_not_add_filters():
    """
    Tests to make sure no filters are applied, based on its empty 'parent_lookup_kwargs'
    value.
    """
    models.Repository.objects.create(name="foo")
    viewset = viewsets.RepositoryViewSet()
    viewset.kwargs = {"name": "foo"}
    queryset = viewset.get_queryset()
    expected = models.Repository.objects.all()

    assertQuerysetEqual(queryset, expected)


def test_must_define_serializer_class():
    """
    Test that get_serializer_class() raises an AssertionError if you don't define the
    serializer_class attribute.
    """

    class TestTaskViewSet(viewsets.NamedModelViewSet):
        minimal_serializer_class = serializers.MinimalTaskSerializer

    with pytest.raises(AssertionError):
        TestTaskViewSet().get_serializer_class()


def test_serializer_class():
    """
    Tests that get_serializer_class() returns the serializer_class attribute if it exists,
    and that it doesn't error if no minimal serializer is defined, but minimal=True.
    """

    class TestTaskViewSet(viewsets.NamedModelViewSet):
        serializer_class = serializers.TaskSerializer

    viewset = TestTaskViewSet()
    assert viewset.get_serializer_class() == serializers.TaskSerializer

    request = unittest.mock.MagicMock()
    request.query_params = QueryDict("minimal=True")
    viewset.request = request

    assert viewset.get_serializer_class() == serializers.TaskSerializer


def test_minimal_query_param():
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
    assert viewset.get_serializer_class() == serializers.TaskSerializer
    # Test that it uses the full serializer with minimal=False
    request.query_params = QueryDict("minimal=False")
    viewset.request = request
    assert viewset.get_serializer_class() == serializers.TaskSerializer
    # Test that it uses the minimal serializer with minimal=True
    request.query_params = QueryDict("minimal=True")
    viewset.request = request
    assert viewset.get_serializer_class() == serializers.MinimalTaskSerializer


@pytest.mark.django_db
def test_no_parent_object():
    """
    Tests that get_parent_field_and_object() raises django.http.Http404 if the parent object
    does not exist on a nested viewset.
    """
    viewset = viewsets.RepositoryVersionViewSet()
    viewset.kwargs = {"repository_pk": 500}

    with pytest.raises(Http404):
        viewset.get_parent_field_and_object()


@pytest.mark.django_db
def test_get_parent_field_and_object():
    """
    Tests that get_parent_field_and_object() returns the correct parent field and parent
    object.
    """
    repo = models.Repository.objects.create(name="foo")
    viewset = viewsets.RepositoryVersionViewSet()
    viewset.kwargs = {"repository_pk": repo.pk}

    assert viewset.get_parent_field_and_object() == ("repository", repo)


@pytest.mark.django_db
def test_get_parent_object():
    """
    Tests that get_parent_object() returns the correct parent object.
    """
    repo = models.Repository.objects.create(name="foo")
    viewset = viewsets.RepositoryVersionViewSet()
    viewset.kwargs = {"repository_pk": repo.pk}

    assert viewset.get_parent_object() == repo


def test_get_nest_depth():
    """
    Test that _get_nest_depth() returns the correct nesting depths.
    """
    assert viewsets.RepositoryViewSet._get_nest_depth() == 1
    assert viewsets.RepositoryVersionViewSet._get_nest_depth() == 2
