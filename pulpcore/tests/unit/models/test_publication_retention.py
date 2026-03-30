import hashlib
import uuid

import pytest

from pulpcore.app.models import (
    Content,
    ContentArtifact,
    DistributedPublication,
    PublishedArtifact,
)
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


def dist_factory(repo=None, repover=None, pub=None, name=None):
    assert [repo, repover, pub].count(
        None
    ) == 2, "Exactly one of repo, repover, or pub must be provided"
    name = name or f"dist-{uuid.uuid4().hex[:8]}"
    return FileDistribution.objects.create(
        name=name, base_path=name, repository=repo, repository_version=repover, publication=pub
    )


def update_dist(dist, repo=UNSET, repover=UNSET, pub=UNSET):
    assert (repo, repover, pub).count(
        UNSET
    ) == 2, "Exactly one of repo, repover, or pub must be provided"
    if repo is not UNSET:
        dist.repository = repo
    if repover is not UNSET:
        dist.repository_version = repover
    if pub is not UNSET:
        dist.publication = pub
    dist.save()


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
        assert repo_version.content.filter(
            pk=ca.content_id
        ).exists(), f"{path!r} not found in repository version content"
    for path in remove or []:
        ca = ContentArtifact.objects.get(relative_path=path)
        assert not repo_version.content.filter(
            pk=ca.content_id
        ).exists(), f"{path!r} should not be in repository version content after removal"
    return repo_version


@pytest.mark.django_db
class TestDistributedPublication:
    def test_created_when_publication_added_to_distribution(self, db):
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        active = DistributedPublication.get_active(dist)
        assert active.count() == 1
        assert active.first().publication_id == pub.pk
        assert active.first().expires_at is None

    def test_first_distributed_publication_is_active(self, db):
        dist = dist_factory(pub=pub_factory())
        assert DistributedPublication.get_active(dist).count() == 1
        assert DistributedPublication.get_expired(dist).count() == 0

    def test_switching_publication_expires_old_and_activates_new(self, db):
        pub1 = pub_factory()
        dist = dist_factory(pub=pub1)

        pub2 = pub_factory()
        update_dist(dist, pub=pub2)

        active = DistributedPublication.get_active(dist)
        assert active.count() == 2
        assert active.filter(expires_at__isnull=True).first().publication_id == pub2.pk
        assert active.filter(expires_at__isnull=False).first().publication_id == pub1.pk


@pytest.mark.django_db
class TestClearDistributedPublication:
    def test_deleting_publication_clears_dps(self, db):
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        assert DistributedPublication.objects.filter(distribution=dist).exists()
        pub.delete()
        assert not DistributedPublication.objects.filter(distribution=dist).exists()

    def test_deleting_older_repository_version_doesnt_clear_dps(self, db):
        repo = FileRepository.objects.create(name="test-repo")
        v1 = repo.latest_version()
        v2 = create_version(repo, add=["some-file.txt"])
        pub = pub_factory(v2)
        dist = dist_factory(pub=pub)
        assert DistributedPublication.objects.filter(distribution=dist).count() == 1
        v1.delete()
        assert DistributedPublication.objects.filter(distribution=dist).count() == 1

    def test_deleting_repository_clears_dps(self, db):
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        repo = pub.repository_version.repository
        assert DistributedPublication.objects.filter(distribution=dist).exists()
        repo.delete()
        assert not DistributedPublication.objects.filter(distribution=dist).exists()


@pytest.mark.django_db
class TestGetFallbackCa:
    def test_returns_ca_when_content_in_publication(self, version_with_content, expected_ca):
        pub_with_a = pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_none_when_content_not_in_publication(self, version_without_content):
        pub_without_a = pub_factory(version_without_content, pass_through=True)
        dist = dist_factory(pub=pub_without_a)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_when_no_published_artifact(self, version_with_content):
        pub_with_a = pub_factory(version_with_content, pass_through=False, create_pa=False)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_ca_via_published_artifact(self, version_with_content, expected_ca):
        pub_with_a = pub_factory(version_with_content, pass_through=False, create_pa=True)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_ca_from_superseded_publication(
        self, version_with_content, version_without_content, expected_ca
    ):
        pub_with_a = pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(pub=pub_with_a)
        pub_without_a = pub_factory(version_without_content, pass_through=True)
        update_dist(dist, pub=pub_without_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_none_after_unsetting_repository(self, version_with_content, expected_ca):
        repo = version_with_content.repository
        pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(repo=repo)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

        update_dist(dist, repo=None)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_after_unsetting_repository_version(
        self, version_with_content, expected_ca
    ):
        pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(repover=version_with_content)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

        update_dist(dist, repover=None)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_after_removing_publication(self, version_with_content, expected_ca):
        pub = pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(pub=pub)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

        update_dist(dist, pub=None)
        assert dist.get_fallback_ca(self.content_path) is None

    @pytest.fixture
    def version_with_content(self, db):
        repo = FileRepository.objects.create(name="test-repo")
        self.content_path = "test.txt"
        return create_version(repo, add=["test.txt"])

    @pytest.fixture
    def version_without_content(self, version_with_content):
        repo = version_with_content.repository
        return create_version(repo, add=["other.txt"], remove=[self.content_path])

    @pytest.fixture
    def expected_ca(self, version_with_content):
        return ContentArtifact.objects.get(relative_path=self.content_path)
