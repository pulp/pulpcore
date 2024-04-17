import pytest
from uuid import uuid4

from pulpcore.app.models import AutoAddObjPermsMixin, Repository
from pulp_file.app.models import FileRepository, FileRemote


@pytest.mark.django_db
def test_cast(django_assert_num_queries):
    remote = FileRemote.objects.create(name=str(uuid4()))
    repository = FileRepository.objects.create(name=str(uuid4()), remote=remote)

    # Test with bare
    with django_assert_num_queries(1):
        repository = Repository.objects.get(name=repository.name)
    with django_assert_num_queries(1):
        repository = repository.cast()
    assert isinstance(repository, FileRepository)
    with django_assert_num_queries(1):
        assert repository.remote.pk == remote.pk

    # Test with read remote
    with django_assert_num_queries(1):
        repository = Repository.objects.get(name=repository.name)
    with django_assert_num_queries(1):
        repository.remote
    with django_assert_num_queries(1):
        repository = repository.cast()
    assert isinstance(repository, FileRepository)
    with django_assert_num_queries(0):
        # Remote is still prefetched.
        assert repository.remote.pk == remote.pk

    # Test with select related
    with django_assert_num_queries(1):
        # Fetch Repository and related remote in join query
        repository = Repository.objects.select_related("remote").get(name=repository.name)
    with django_assert_num_queries(1):
        repository = repository.cast()
    assert isinstance(repository, FileRepository)
    with django_assert_num_queries(0):
        # Remote is still prefetched.
        assert repository.remote.pk == remote.pk

    # Test with prefetch related
    with django_assert_num_queries(2):
        # Fetch Repository and related remote (-> 2 queries)
        repository = Repository.objects.prefetch_related("remote").get(name=repository.name)
    with django_assert_num_queries(1):
        repository = repository.cast()
    assert isinstance(repository, FileRepository)
    with django_assert_num_queries(0):
        # Remote is still prefetched.
        assert repository.remote.pk == remote.pk


def test_get_model_for_pulp_type():
    assert Repository.get_model_for_pulp_type("core.repository") is Repository
    assert Repository.get_model_for_pulp_type("file.file") is FileRepository


class PermissionRepository(Repository, AutoAddObjPermsMixin):
    class Meta:
        app_label = "test"
        default_related_name = "permission_repository"
        proxy = True


@pytest.mark.django_db
def test_resiliant_auto_perms():
    PermissionRepository(name="auto permission test").save()
