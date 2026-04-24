"""Tests for the distributed publication grace-period feature."""

import time
from dataclasses import dataclass
from urllib.parse import urljoin

import pytest
import requests
from django.conf import settings

from pulpcore.client.pulp_file import FileFileDistribution, FileFilePublication, RepositorySyncURL


@dataclass
class DistributionPublicationContext:
    pub_with_file: FileFilePublication
    pub_without_file: FileFilePublication

    def create_distribution(self, publication: FileFilePublication) -> FileFileDistribution:
        raise NotImplementedError

    def update_distribution(self, dist: FileFileDistribution, publication: FileFilePublication):
        raise NotImplementedError

    def get_file_url(self, distribution: FileFileDistribution) -> str:
        raise NotImplementedError

    def clear_dist_cache(self, dist: FileFileDistribution) -> None:
        raise NotImplementedError

    def wait_retention_period(self):
        assert settings.DISTRIBUTED_PUBLICATION_RETENTION_PERIOD <= 5, (
            "DISTRIBUTED_PUBLICATION_RETENTION_PERIOD is too long for testing."
        )
        time.sleep(settings.DISTRIBUTED_PUBLICATION_RETENTION_PERIOD + 1)


class TestDistributionPublicationRetention:
    @pytest.mark.parallel
    def test_old_content_is_served_within_retention_period(
        self,
        ctx: DistributionPublicationContext,
    ):
        """Old content is still served immediately after switching to a new publication."""
        dist = ctx.create_distribution(publication=ctx.pub_with_file)
        file_url = ctx.get_file_url(dist)
        assert requests.get(file_url).status_code == 200

        ctx.update_distribution(dist, publication=ctx.pub_without_file)
        assert requests.get(file_url).status_code == 200

    @pytest.mark.parallel
    def test_old_content_expires_after_retention_period(
        self,
        ctx: DistributionPublicationContext,
    ):
        """Old content becomes unavailable once the retention period expires."""
        dist = ctx.create_distribution(publication=ctx.pub_with_file)
        file_url = ctx.get_file_url(dist)

        ctx.update_distribution(dist, publication=ctx.pub_without_file)
        ctx.wait_retention_period()
        ctx.clear_dist_cache(dist)  # if redis is enabled it interferes with the assertion
        assert requests.get(file_url).status_code == 404

    @pytest.fixture
    def ctx(
        self,
        file_bindings,
        file_repository_factory,
        file_remote_ssl_factory,
        basic_manifest_path,
        file_publication_factory,
        file_distribution_factory,
        distribution_base_url,
        monitor_task,
    ) -> DistributionPublicationContext:
        """Set up two publications: one with a file, one without."""
        repo = file_repository_factory()
        remote = file_remote_ssl_factory(manifest_path=basic_manifest_path, policy="immediate")

        # Sync to get files into the repo
        monitor_task(
            file_bindings.RepositoriesFileApi.sync(
                repo.pulp_href, RepositorySyncURL(remote=remote.pulp_href)
            ).task
        )
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

        # Publish version 1 (has the file)
        pub_with_file = file_publication_factory(repository=repo.pulp_href)

        # Pick a file that exists in pub_with_file
        content = file_bindings.ContentFilesApi.list(
            repository_version=repo.latest_version_href
        ).results[0]
        file_relative_path = content.relative_path

        # Remove the file from the repo
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                repo.pulp_href, {"remove_content_units": [content.pulp_href]}
            ).task
        )
        repo = file_bindings.RepositoriesFileApi.read(repo.pulp_href)

        # Publish version 2 (does not have the file)
        pub_without_file = file_publication_factory(repository=repo.pulp_href)

        class _DistributionPublicationContext(DistributionPublicationContext):
            def create_distribution(self, publication: FileFilePublication) -> FileFileDistribution:
                return file_distribution_factory(publication=publication.pulp_href)

            def update_distribution(
                self, dist: FileFileDistribution, publication: FileFilePublication
            ) -> None:
                monitor_task(
                    file_bindings.DistributionsFileApi.partial_update(
                        dist.pulp_href, {"publication": publication.pulp_href}
                    ).task
                )

            def get_file_url(self, distribution: FileFileDistribution) -> str:
                return urljoin(distribution_base_url(distribution.base_url), file_relative_path)

            def clear_dist_cache(self, dist: FileFileDistribution) -> None:
                original_base_path = dist.base_path
                tmp_base_path = original_base_path + "-tmp"
                monitor_task(
                    file_bindings.DistributionsFileApi.partial_update(
                        dist.pulp_href, {"base_path": tmp_base_path}
                    ).task
                )
                monitor_task(
                    file_bindings.DistributionsFileApi.partial_update(
                        dist.pulp_href, {"base_path": original_base_path}
                    ).task
                )
                restored = file_bindings.DistributionsFileApi.read(dist.pulp_href)
                assert restored.base_path == original_base_path

        return _DistributionPublicationContext(
            pub_with_file=pub_with_file,
            pub_without_file=pub_without_file,
        )
