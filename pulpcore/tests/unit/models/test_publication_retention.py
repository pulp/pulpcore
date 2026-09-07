import hashlib
import uuid
from datetime import timedelta
from unittest import mock

import pytest

from pulpcore.app.models import (
    Content,
    ContentArtifact,
    DistributedPublication,
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


def dist_factory(repo=None, repover=None, pub=None, name=None):
    assert [repo, repover, pub].count(None) == 2, (
        "Exactly one of repo, repover, or pub must be provided"
    )
    name = name or f"dist-{uuid.uuid4().hex[:8]}"
    return FileDistribution.objects.create(
        name=name, base_path=name, repository=repo, repository_version=repover, publication=pub
    )


def update_dist(dist, repo=UNSET, repover=UNSET, pub=UNSET):
    assert (repo, repover, pub).count(UNSET) == 2, (
        "Exactly one of repo, repover, or pub must be provided"
    )
    # Clear the other fields to ensure mutual exclusivity
    if repo is not UNSET:
        dist.publication = None
        dist.repository_version = None
        dist.repository = repo
    if repover is not UNSET:
        dist.publication = None
        dist.repository = None
        dist.repository_version = repover
    if pub is not UNSET:
        dist.repository = None
        dist.repository_version = None
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
class TestDistributedPublication:
    def test_created_when_publication_added_to_distribution(self, db):
        """Setting a publication on a distribution records it as the active DistributedPublication."""
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        non_expired = DistributedPublication.get_non_expired(include_current=True).filter(
            distribution=dist
        )
        assert non_expired.count() == 1
        assert non_expired.first().publication_id == pub.pk
        assert non_expired.first().expires_at is None

    def test_mark_expiration_on_old_and_activate_new_when_publication_switched(self, db):
        """Switching a distribution's publication activates the new one and expires the old one."""
        pub1 = pub_factory()
        dist = dist_factory(pub=pub1)

        pub2 = pub_factory()
        update_dist(dist, pub=pub2)

        non_expired = DistributedPublication.get_non_expired(include_current=True).filter(
            distribution=dist
        )
        assert non_expired.count() == 2
        assert non_expired.filter(expires_at__isnull=True).first().publication_id == pub2.pk
        assert non_expired.filter(expires_at__isnull=False).first().publication_id == pub1.pk

    def test_deleted_when_publication_deleted(self, db):
        """Deleting the publication removes its DistributedPublication records."""
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        assert DistributedPublication.objects.filter(distribution=dist).exists()
        pub.delete()
        assert not DistributedPublication.objects.filter(distribution=dist).exists()

    def test_deleted_when_repository_deleted(self, db):
        """Deleting the repository cascades away its DistributedPublication records."""
        pub = pub_factory()
        dist = dist_factory(pub=pub)
        repo = pub.repository_version.repository
        assert DistributedPublication.objects.filter(distribution=dist).exists()
        repo.delete()
        assert not DistributedPublication.objects.filter(distribution=dist).exists()

    def test_unaffected_when_older_repository_version_deleted(self, db):
        """Deleting an older, unrelated repository_version leaves the distribution's DPs intact."""
        repo = FileRepository.objects.create(name="test-repo")
        v1 = repo.latest_version()
        v2 = create_version(repo, add=["some-file.txt"])
        pub = pub_factory(v2)
        dist = dist_factory(pub=pub)
        assert DistributedPublication.objects.filter(distribution=dist).count() == 1
        v1.delete()
        assert DistributedPublication.objects.filter(distribution=dist).count() == 1

    def test_created_when_new_publication_for_distributed_repository(self, db):
        """A distribution serving a repository directly indirectly distributes the latest
        publication. Creating a new publication should record it as distributed."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist = dist_factory(repo=repo)
        pub = publish(version)
        assert DistributedPublication.objects.filter(distribution=dist, publication=pub).exists()

    def test_created_when_new_publication_for_distributed_repository_version(self, db):
        """A distribution serving a repository_version (with SERVE_FROM_PUBLICATION) indirectly
        distributes the latest publication of that version. Creating a new publication for
        that version should record it as distributed."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist = dist_factory(repover=version)
        pub = publish(version)
        assert DistributedPublication.objects.filter(distribution=dist, publication=pub).exists()

    def test_reuses_non_expired_distributed_publication(self, db):
        """If a distribution is updated to serve a publication for which a DistributedPublication
        already exists (but is expiring, not active), that DP should be reactivated and there should
        not be a duplicate."""
        pub1 = pub_factory()
        pub2 = pub_factory()
        dist = dist_factory(pub=pub1)
        # dist→pub1: DP(pub1, expires_at=NULL)
        assert (
            DistributedPublication.objects.filter(
                distribution=dist, publication=pub1, expires_at__isnull=True
            ).count()
            == 1
        )

        # Switch to pub2: DP(pub1) gets expires_at set, DP(pub2, expires_at=NULL) created
        update_dist(dist, pub=pub2)
        dp_pub1_old = DistributedPublication.objects.get(distribution=dist, publication=pub1)
        assert dp_pub1_old.expires_at is not None
        assert (
            DistributedPublication.objects.filter(
                distribution=dist, publication=pub2, expires_at__isnull=True
            ).count()
            == 1
        )

        # Switch back to pub1: should reactivate the existing DP(pub1), not create a new one
        dist.refresh_from_db()
        update_dist(dist, pub=pub1)
        all_dps_pub1 = DistributedPublication.objects.filter(distribution=dist, publication=pub1)
        assert all_dps_pub1.count() == 1, (
            f"Should reuse existing DP, not create duplicate. "
            f"Found {all_dps_pub1.count()} DPs for pub1"
        )
        dp_pub1_reactivated = all_dps_pub1.first()
        assert dp_pub1_reactivated.pk == dp_pub1_old.pk, (
            "Should be the same DP instance, reactivated"
        )
        assert dp_pub1_reactivated.expires_at is None, "Should clear expires_at when reactivating"
        # Reactivating pub1 must also expire pub2, leaving exactly one active DP overall.
        active = DistributedPublication.objects.filter(distribution=dist, expires_at__isnull=True)
        assert active.count() == 1, f"Exactly one active DP expected, found {active.count()}"
        assert active.first().publication_id == pub1.pk

    def test_creates_distributed_publications_for_multiple_distributions(self, db):
        """Creating a publication should track it in DistributedPublication for ALL affected
        distributions, regardless of whether they serve via repository or repository_version."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])

        dist1 = dist_factory(repo=repo)
        dist2 = dist_factory(repover=version)
        dist3 = dist_factory(repo=repo)

        pub = publish(version)

        assert DistributedPublication.objects.filter(distribution=dist1, publication=pub).exists()
        assert DistributedPublication.objects.filter(distribution=dist2, publication=pub).exists()
        assert DistributedPublication.objects.filter(distribution=dist3, publication=pub).exists()

    def test_records_new_and_expires_old_when_repository_version_switched(self, db):
        """Repointing a distribution from one repository_version to another should record the new
        version's publication as active and mark the previously-served one as expiring. This
        exercises the same logic as switching publications, but through the repository_version FK.
        """
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        pub1 = pub_factory(v1, pass_through=True)
        pub2 = pub_factory(v2, pass_through=True)
        dist = dist_factory(repover=v1)
        assert (
            DistributedPublication.objects.filter(
                distribution=dist, publication=pub1, expires_at__isnull=True
            ).count()
            == 1
        )

        update_dist(dist, repover=v2)
        assert DistributedPublication.objects.filter(
            distribution=dist, publication=pub2, expires_at__isnull=True
        ).exists()
        assert DistributedPublication.objects.filter(
            distribution=dist, publication=pub1, expires_at__isnull=False
        ).exists()

    def test_reuses_expiring_dp_when_repository_version_switched_back(self, db):
        """Switching back to a previously-served repository_version should reactivate the existing
        (expiring) DistributedPublication rather than create a duplicate."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        pub1 = pub_factory(v1, pass_through=True)
        pub_factory(v2, pass_through=True)
        dist = dist_factory(repover=v1)

        update_dist(dist, repover=v2)
        dp_pub1_expiring = DistributedPublication.objects.get(distribution=dist, publication=pub1)
        assert dp_pub1_expiring.expires_at is not None

        dist.refresh_from_db()
        update_dist(dist, repover=v1)
        dps_pub1 = DistributedPublication.objects.filter(distribution=dist, publication=pub1)
        assert dps_pub1.count() == 1, "should reactivate existing DP, not create a duplicate"
        assert dps_pub1.first().pk == dp_pub1_expiring.pk
        assert dps_pub1.first().expires_at is None, "should clear expires_at when reactivating"

    def test_protected_from_deletion_while_served_by_distribution(self, db):
        """A repository_version served directly by a distribution is protected: it cannot be
        deleted until the distribution is repointed."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        pub_factory(v2, pass_through=True)
        dist_factory(repover=v2)
        with pytest.raises(Exception, match="cannot be deleted"):
            v2.delete()

    def test_multiple_publications_of_same_version_tracked_separately(self, db):
        """Creating multiple publications of the same version should track each one separately:
        the newest becomes active and the older one starts expiring."""
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist = dist_factory(repover=version)

        pub1 = publish(version)
        assert DistributedPublication.objects.filter(
            distribution=dist, publication=pub1, expires_at__isnull=True
        ).exists()

        pub2 = publish(version)
        # pub2 is now active, pub1 is expiring
        assert DistributedPublication.objects.filter(
            distribution=dist, publication=pub2, expires_at__isnull=True
        ).exists()
        assert DistributedPublication.objects.filter(
            distribution=dist, publication=pub1, expires_at__isnull=False
        ).exists()
        # Both DPs coexist within the retention window
        assert DistributedPublication.objects.filter(distribution=dist).count() == 2


@pytest.mark.django_db
class TestGetFallbackCa:
    def test_returns_ca_when_content_in_publication(self, version_with_content, expected_ca):
        """Returns the content artifact when the served publication contains the content."""
        pub_with_a = pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_none_when_content_not_in_publication(self, version_without_content):
        """Returns None when the served publication does not contain the content."""
        pub_without_a = pub_factory(version_without_content, pass_through=True)
        dist = dist_factory(pub=pub_without_a)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_when_no_published_artifact(self, version_with_content):
        """Returns None for a non-pass-through publication with no matching PublishedArtifact."""
        pub_with_a = pub_factory(version_with_content, pass_through=False, create_pa=False)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_ca_when_content_accessible_via_published_artifact(
        self, version_with_content, expected_ca
    ):
        """Returns the content artifact reachable through a PublishedArtifact (non-pass-through)."""
        pub_with_a = pub_factory(version_with_content, pass_through=False, create_pa=True)
        dist = dist_factory(pub=pub_with_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_ca_when_content_only_in_superseded_publication(
        self, version_with_content, version_without_content, expected_ca
    ):
        """Returns the content artifact from a superseded (expiring) publication still within
        the retention window."""
        pub_with_a = pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(pub=pub_with_a)
        pub_without_a = pub_factory(version_without_content, pass_through=True)
        update_dist(dist, pub=pub_without_a)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

    def test_returns_none_when_repository_unset(self, version_with_content, expected_ca):
        """Returns None once the distribution's repository is cleared."""
        repo = version_with_content.repository
        pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(repo=repo)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

        update_dist(dist, repo=None)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_when_repository_version_unset(self, version_with_content, expected_ca):
        """Returns None once the distribution's repository_version is cleared."""
        pub_factory(version_with_content, pass_through=True)
        dist = dist_factory(repover=version_with_content)
        assert dist.get_fallback_ca(self.content_path) == expected_ca

        update_dist(dist, repover=None)
        assert dist.get_fallback_ca(self.content_path) is None

    def test_returns_none_when_publication_removed(self, version_with_content, expected_ca):
        """Returns None once the distribution's publication is cleared."""
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

    def test_invalidates_when_repository_version_switched(self, settings):
        """Repointing a distribution to a different repository_version invalidates its cache."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        pub_factory(v1, pass_through=True)
        pub_factory(v2, pass_through=True)
        dist = dist_factory(repover=v1)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            update_dist(dist, repover=v2)
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)


@pytest.mark.django_db
class TestCacheInvalidationOnPublicationCreate:
    """
    Creating a new publication changes the content served by every distribution that
    indirectly distributes that publication's repository/repository_version. The cache
    must be invalidated for all of them, not just the ones with a direct ``repository`` FK.
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

    def test_invalidates_repository_version_distribution(self, settings):
        """Creating a publication invalidates a distribution serving via its repository_version."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        dist = dist_factory(repover=version)
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

    def test_invalidates_only_relevant_distributions_in_mixed_scenario(self, settings):
        """With mixed distribution types, creating a publication for v1 should invalidate the
        repository distribution and the v1 distribution, but not the v2 distribution."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        v1 = create_version(repo, add=["v1.txt"])
        v2 = create_version(repo, add=["v2.txt"])
        dist_repo = dist_factory(repo=repo)
        dist_v1 = dist_factory(repover=v1)
        dist_v2 = dist_factory(repover=v2)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            publish(v1)
        invalidated = invalidated_base_paths(mock_cache)
        assert cache_key(dist_repo.base_path) in invalidated, "repo dist should be invalidated"
        assert cache_key(dist_v1.base_path) in invalidated, "v1 dist should be invalidated"
        assert cache_key(dist_v2.base_path) not in invalidated, "v2 dist should NOT be invalidated"


@pytest.mark.django_db
class TestCacheInvalidationOnPublicationDelete:
    """
    Deleting the publication currently served by a distribution changes what that distribution
    serves, so its cache must be invalidated - including distributions that serve the
    publication indirectly through their repository_version.
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

    def test_invalidates_repository_version_distribution_when_latest_deleted(self, settings):
        """Deleting a version's latest publication invalidates a repository_version distribution."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        pub = pub_factory(version, pass_through=True)
        dist = dist_factory(repover=version)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            pub.delete()
        assert cache_key(dist.base_path) in invalidated_base_paths(mock_cache)

    # -- Negative cases: the deleted publication is NOT what the distribution serves --

    def test_ignores_repository_version_distribution_of_unrelated_version(self, settings):
        """Deleting a publication of one version must not invalidate a distribution serving a
        different version."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version1 = create_version(repo, add=["v1.txt"])
        version2 = create_version(repo, add=["v2.txt"])
        pub2 = pub_factory(version2, pass_through=True)
        dist = dist_factory(repover=version1)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            pub2.delete()
        assert cache_key(dist.base_path) not in invalidated_base_paths(mock_cache)

    def test_ignores_repository_version_distribution_when_superseded_deleted(self, settings):
        """Deleting an older (non-latest) publication of the served version must not invalidate the
        repository_version distribution, which still serves the newer publication."""
        settings.CACHE_ENABLED = True
        repo = FileRepository.objects.create(name=f"repo-{uuid.uuid4().hex[:8]}")
        version = create_version(repo, add=["some-file.txt"])
        old_pub = pub_factory(version, pass_through=True)
        new_pub = pub_factory(version, pass_through=True)
        # Force deterministic ordering (pulp_created is auto_now_add).
        FilePublication.objects.filter(pk=old_pub.pk).update(
            pulp_created=new_pub.pulp_created - timedelta(seconds=1)
        )
        dist = dist_factory(repover=version)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            old_pub.delete()
        assert cache_key(dist.base_path) not in invalidated_base_paths(mock_cache)

    def test_ignores_repository_distribution_when_deleted_not_latest_for_repository(self, settings):
        """Deleting a publication that is the latest for its version but not the latest for the
        repository should invalidate the repository_version distribution, but not the
        repository distribution (which still serves a newer publication).
        """
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
        dist_repo = dist_factory(repo=repo)  # serves pub2 (latest of latest version)
        dist_v1 = dist_factory(repover=v1)  # serves pub1 (latest of v1)
        with mock.patch("pulpcore.app.models.publication.Cache") as mock_cache:
            pub1.delete()
        invalidated = invalidated_base_paths(mock_cache)
        assert cache_key(dist_v1.base_path) in invalidated, "v1 dist should be invalidated"
        assert cache_key(dist_repo.base_path) not in invalidated, (
            "repo dist should NOT be invalidated (pub2 still latest)"
        )
