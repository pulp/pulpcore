import hashlib
import uuid
from datetime import timedelta
from unittest import mock

import pytest

from pulpcore.app.models import (
    Content,
    ContentArtifact,
    PublishedArtifact,
)
from pulpcore.app.util import cache_key

from pulp_file.app.models import (
    FileContent,
    FileDistribution,
    FilePublication,
    FileRepository,
)

UNSET = object()


def pub_factory(repo_version=None, pass_through=False, create_pa=False):
    if repo_version is None:
        repo_version = FileRepository.objects.create(
            name=f"repo-{uuid.uuid4().hex[:8]}"
        ).versions.first()
    pub = FilePublication.objects.create(
        repository_version=repo_version, complete=True, pass_through=pass_through
    )
    if create_pa:
        for ca in ContentArtifact.objects.filter(content__in=repo_version.content.all()):
            PublishedArtifact.objects.create(
                publication=pub, content_artifact=ca, relative_path=ca.relative_path
            )
    return pub


def dist_factory(repo=None, pub=None, name=None):
    assert [repo, pub].count(None) == 1, "Exactly one of repo or pub must be provided"
    name = name or f"dist-{uuid.uuid4().hex[:8]}"
    return FileDistribution.objects.create(
        name=name, base_path=name, repository=repo, publication=pub
    )


def update_dist(dist, repo=UNSET, pub=UNSET):
    assert (repo, pub).count(UNSET) == 1, "Exactly one of repo or pub must be provided"
    # Clear the other fields to ensure mutual exclusivity
    if repo is not UNSET:
        dist.publication = None
        dist.repository = repo
    if pub is not UNSET:
        dist.repository = None
        dist.publication = pub
    dist.save()


def publish(repo_version, pass_through=True):
    """
    Create and complete a publication through the Publication context manager.

    `CreatedResource` is mocked out because it requires a current Task, which isn't set up in
    unit tests. This still runs the `__exit__` finalization that invalidates caches and records
    distributed publications.
    """
    with mock.patch("pulpcore.app.models.publication.CreatedResource"):
        with FilePublication.create(repo_version, pass_through=pass_through) as pub:
            pass
    return pub


def invalidated_base_paths(mock_cache):
    """Collect the set of base_paths passed to a mocked `Cache().delete`."""
    paths = set()
    for call in mock_cache.return_value.delete.call_args_list:
        base_key = call.kwargs.get("base_key")
        if base_key is None and call.args:
            base_key = call.args[0]
        if isinstance(base_key, str):
            paths.add(base_key)
        elif base_key is not None:
            paths.update(base_key)
    return paths


def create_version(repo, add=None, remove=None):
    """
    Create a RepositoryVersion adding and/or removing content by path.
    """
    assert add or remove, "at least one of add or remove must be specified"
    with repo.new_version() as repo_version:
        for path in add or []:
            digest = hashlib.sha256(path.encode()).hexdigest()
            content = FileContent.objects.create(relative_path=path, digest=digest)
            repo_version.add_content(Content.objects.filter(pk=content.pk))
            ContentArtifact.objects.create(content=content, relative_path=path)
        for path in remove or []:
            ca = ContentArtifact.objects.get(relative_path=path)
            repo_version.remove_content(Content.objects.filter(pk=ca.content_id))
    for path in add or []:
        ca = ContentArtifact.objects.get(relative_path=path)
        assert repo_version.content.filter(pk=ca.content_id).exists(), (
            f"{path!r} not found in repository version content"
        )
    for path in remove or []:
        ca = ContentArtifact.objects.get(relative_path=path)
        assert not repo_version.content.filter(pk=ca.content_id).exists(), (
            f"{path!r} should not be in repository version content after removal"
        )
    return repo_version


@pytest.mark.django_db
class TestCacheInvalidationOnDistributionUpdate:
    """
    Repointing a distribution changes the content it serves, so its cache must be invalidated.
    """

    def test_invalidates_when_publication_switched(self, settings):
        """Repointing a distribution to a different publication invalidates its cache."""
        settings.CACHE_ENABLED = True
        pub1 = pub_factory(pass_through=True)
        pub2 = pub_factory(pass_through=True)
        dist = dist_factory(pub=pub1)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            update_dist(dist, pub=pub2)
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)

    def test_invalidates_when_repository_switched(self, settings):
        """Repointing a distribution to a different repository invalidates its cache."""
        settings.CACHE_ENABLED = True
        repo1 = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        repo2 = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        create_version(repo1, add=["v1.txt"])
        create_version(repo2, add=["v2.txt"])
        dist = dist_factory(repo=repo1)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            update_dist(dist, repo=repo2)
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)


@pytest.mark.django_db
class TestCacheInvalidationOnPublicationCreate:
    """
    Creating a new publication changes the content served by distributions that resolve the
    latest publication for their repository. Their caches must be invalidated.
    """

    def test_invalidates_repository_distribution(self, settings):
        """Creating a publication invalidates a distribution serving via its repository."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist = dist_factory(repo=repo)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            publish(version)
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)

    def test_invalidates_multiple_distributions_on_same_repository(self, settings):
        """Creating a publication must invalidate ALL distributions serving that repository."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist1 = dist_factory(repo=repo)
        dist2 = dist_factory(repo=repo)
        dist3 = dist_factory(repo=repo)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            publish(version)
        invalidated = invalidated_base_paths(mock_cache)
        assert cache_key(dist1.base_path) in invalidated
        assert cache_key(dist2.base_path) in invalidated
        assert cache_key(dist3.base_path) in invalidated

    def test_invalidates_repository_distribution_for_older_version(self, settings):
        """Publishing an older repository version still invalidates the repository distribution."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        create_version(repo, add=["v2.txt"])
        dist_repo = dist_factory(repo=repo)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            publish(v1)
        invalidated = invalidated_base_paths(mock_cache)
        assert cache_key(dist_repo.base_path) in invalidated, "repo dist should be invalidated"


@pytest.mark.django_db
class TestCacheInvalidationOnPublicationDelete:
    """
    Deleting the publication currently served by a distribution changes what that distribution
    serves, so its cache must be invalidated.
    """

    # -- Positive cases: the deleted publication is what the distribution serves --

    def test_invalidates_repository_distribution_when_latest_deleted(self, settings):
        """Deleting the repository's latest publication invalidates a repository distribution."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        pub = pub_factory(version, pass_through=True)
        dist = dist_factory(repo=repo)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            pub.delete()
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)

    # -- Negative cases: the deleted publication is NOT what the distribution serves --

    def test_ignores_repository_distribution_when_deleted_not_latest_for_repository(self, settings):
        """Deleting an older publication must not invalidate the repository distribution."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        pub1 = pub_factory(v1, pass_through=True)
        pub2 = pub_factory(v2, pass_through=True)
        # Force pub2 to be the newest (latest for the repository).
        FilePublication.objects.filter(pk=pub1.pk).update(
            pulp_created=pub2.pulp_created - timedelta(seconds=1)
        )
        dist_repo = dist_factory(repo=repo)  # serves pub2, which remains the latest publication
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            pub1.delete()
        invalidated = invalidated_base_paths(mock_cache)
        assert cache_key(dist_repo.base_path) not in invalidated, (
            "repo dist should NOT be invalidated (pub2 still latest)"
        )


@pytest.mark.django_db
class TestCacheInvalidationOnRepositoryVersionCreate:
    """
    While a new repository version is being created, the repository's distributions are still
    served from the previous one, and a response computed then can be put into the cache.
    Clearing the cache only when the version is started would leave that response there until
    it expires, so the cache must be cleared once the new version is complete.
    """

    def test_invalidates_once_new_version_is_complete(
        self, settings, django_capture_on_commit_callbacks
    ):
        """Creating a repository version invalidates the cache after the version is complete."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        dist = dist_factory(repo=repo)
        complete_at_invalidation = []

        def record(*args, base_key=None, **kwargs):
            if base_key is not None and cache_key(dist.base_path) in base_key:
                complete_at_invalidation.append(repo.versions.latest("number").complete)

        with mock.patch("pulpcore.app.models.repository.Cache") as mock_cache:
            mock_cache.return_value.delete.side_effect = record
            with django_capture_on_commit_callbacks(execute=True):
                version = create_version(repo, add=["some-file.txt"])
        assert version.complete
        assert True in complete_at_invalidation

    def test_ignores_version_without_changes(self, settings, django_capture_on_commit_callbacks):
        """A new version that changes nothing is discarded and leaves the cache alone."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        dist_factory(repo=repo)
        with mock.patch("pulpcore.app.models.repository.Cache") as mock_cache:
            with django_capture_on_commit_callbacks(execute=True):
                with repo.new_version():
                    pass
        mock_cache.return_value.delete.assert_not_called()
