"""Tests for checkpoint distribution and publications."""

from datetime import datetime, timedelta
import re
from time import sleep
from urllib.parse import urlparse
import uuid
from aiohttp import ClientResponseError
import pytest
from pulpcore.client.pulp_file import exceptions
from pulpcore.content.handler import Handler


@pytest.fixture(scope="class")
def content_factory(tmp_path_factory, file_bindings, monitor_task):
    def _content_factory(name):
        file = tmp_path_factory.mktemp("content") / name
        file.write_text(str(uuid.uuid4()))
        return monitor_task(
            file_bindings.ContentFilesApi.create(relative_path=name, file=str(file)).task
        ).created_resources[0]

    return _content_factory


@pytest.fixture(scope="class")
def setup(
    file_repository_factory,
    file_distribution_factory,
    content_factory,
    file_bindings,
    monitor_task,
):
    def create_publication(repo, checkpoint):
        nonlocal content_counter
        monitor_task(
            file_bindings.RepositoriesFileApi.modify(
                repo.pulp_href, {"add_content_units": [content_factory(f"{content_counter}")]}
            ).task
        )
        content_counter += 1

        response = monitor_task(
            file_bindings.PublicationsFileApi.create(
                {"repository": repo.pulp_href, "checkpoint": checkpoint}
            ).task
        )
        return file_bindings.PublicationsFileApi.read(response.created_resources[0])

    repo = file_repository_factory()
    distribution = file_distribution_factory(repository=repo.pulp_href, checkpoint=True)

    pubs = []
    content_counter = 0
    pubs.append(create_publication(repo, False))
    sleep(1)
    pubs.append(create_publication(repo, True))
    sleep(1)
    pubs.append(create_publication(repo, False))
    sleep(1)
    pubs.append(create_publication(repo, True))
    sleep(1)
    pubs.append(create_publication(repo, False))

    return pubs, distribution


@pytest.fixture
def checkpoint_url(distribution_base_url):
    def _checkpoint_url(distribution, timestamp):
        distro_base_url = distribution_base_url(distribution.base_url)
        return f"{distro_base_url}{Handler._format_checkpoint_timestamp(timestamp)}/"

    return _checkpoint_url


class TestCheckpointDistribution:
    @pytest.mark.parallel
    def test_base_path_lists_checkpoints(self, setup, http_get, distribution_base_url):
        pubs, distribution = setup

        response = http_get(distribution_base_url(distribution.base_url)).decode("utf-8")

        checkpoints_ts = set(re.findall(r"\d{8}T\d{6}Z", response))
        assert len(checkpoints_ts) == 2
        assert Handler._format_checkpoint_timestamp(pubs[1].pulp_created) in checkpoints_ts
        assert Handler._format_checkpoint_timestamp(pubs[3].pulp_created) in checkpoints_ts

    @pytest.mark.parallel
    def test_distro_root_no_trailing_slash_is_redirected(
        self,
        setup,
        http_get,
        distribution_base_url,
    ):
        """Test checkpoint listing when path doesn't end with a slash."""

        pubs, distribution = setup

        # Test a checkpoint distro listing path
        response = http_get(distribution_base_url(distribution.base_url[:-1])).decode("utf-8")
        checkpoints_ts = set(re.findall(r"\d{8}T\d{6}Z", response))

        assert len(checkpoints_ts) == 2
        assert Handler._format_checkpoint_timestamp(pubs[1].pulp_created) in checkpoints_ts
        assert Handler._format_checkpoint_timestamp(pubs[3].pulp_created) in checkpoints_ts

    @pytest.mark.parallel
    def test_timestamped_checkpoint_no_trailing_slash_is_redirected(
        self,
        setup,
        http_get,
        checkpoint_url,
    ):
        """Test a timestamped checkpoint when path doesn't end with a slash."""

        pubs, distribution = setup

        pub_1_url = checkpoint_url(distribution, pubs[1].pulp_created)
        response = http_get(pub_1_url[:-1]).decode("utf-8")

        assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

    @pytest.mark.parallel
    def test_exact_timestamp_is_served(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup

        pub_1_url = checkpoint_url(distribution, pubs[1].pulp_created)
        response = http_get(pub_1_url).decode("utf-8")

        assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

    @pytest.mark.parallel
    def test_invalid_timestamp_returns_404(self, setup, http_get, distribution_base_url):
        _, distribution = setup
        with pytest.raises(ClientResponseError) as exc:
            http_get(distribution_base_url(f"{distribution.base_url}invalid_ts/"))

        assert exc.value.status == 404

        with pytest.raises(ClientResponseError) as exc:
            http_get(distribution_base_url(f"{distribution.base_url}20259928T092752Z/"))

        assert exc.value.status == 404

    @pytest.mark.parallel
    def test_checkpoint_artifact_is_served(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup
        pub_1_url = checkpoint_url(distribution, pubs[1].pulp_created)
        pub_2_url = checkpoint_url(distribution, pubs[2].pulp_created)

        pub_2_response = http_get(f"{pub_2_url}PULP_MANIFEST").decode("utf-8")
        pub_1_response = http_get(f"{pub_1_url}PULP_MANIFEST").decode("utf-8")

        assert pub_2_response == pub_1_response
        lines = pub_1_response.strip().split("\n")
        artifact_names = {line.split(",")[0] for line in lines}
        assert artifact_names == {"0", "1"}

    @pytest.mark.parallel
    def test_non_checkpoint_timestamp_is_redirected(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup
        # Using a non-checkpoint publication timestamp
        pub_3_url = checkpoint_url(distribution, pubs[3].pulp_created)
        pub_4_url = checkpoint_url(distribution, pubs[4].pulp_created)

        response = http_get(pub_4_url).decode("utf-8")
        assert f"<h1>Index of {urlparse(pub_3_url).path}</h1>" in response

        # Test without a trailing slash
        response = http_get(pub_4_url[:-1]).decode("utf-8")
        assert f"<h1>Index of {urlparse(pub_3_url).path}</h1>" in response

    @pytest.mark.parallel
    def test_arbitrary_timestamp_is_redirected(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup
        pub_1_url = checkpoint_url(distribution, pubs[1].pulp_created)
        arbitrary_url = checkpoint_url(distribution, pubs[1].pulp_created + timedelta(seconds=1))

        response = http_get(arbitrary_url).decode("utf-8")
        assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

        # Test without a trailing slash
        response = http_get(arbitrary_url[:-1]).decode("utf-8")
        assert f"<h1>Index of {urlparse(pub_1_url).path}</h1>" in response

    @pytest.mark.parallel
    def test_current_timestamp_serves_latest_checkpoint(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup
        pub_3_url = checkpoint_url(distribution, pubs[3].pulp_created)
        now_url = checkpoint_url(distribution, datetime.now())

        response = http_get(now_url).decode("utf-8")

        assert f"<h1>Index of {urlparse(pub_3_url).path}</h1>" in response

    @pytest.mark.parallel
    def test_before_first_timestamp_returns_404(self, setup, http_get, checkpoint_url):
        pubs, distribution = setup
        pub_0_url = checkpoint_url(distribution, pubs[0].pulp_created)

        with pytest.raises(ClientResponseError) as exc:
            http_get(pub_0_url).decode("utf-8")

        assert exc.value.status == 404

    @pytest.mark.parallel
    def test_future_timestamp_returns_404(self, setup, http_get, checkpoint_url):
        _, distribution = setup
        url = checkpoint_url(distribution, datetime.now() + timedelta(days=1))

        with pytest.raises(ClientResponseError) as exc:
            http_get(url).decode("utf-8")

        assert exc.value.status == 404

    @pytest.mark.parallel
    def test_checkpoint_publication_with_repository_version_fails(
        self, file_bindings, gen_object_with_cleanup, file_repository_factory
    ):
        """Test that creating checkpoint publication using a repository version fails."""

        repo = file_repository_factory()

        with pytest.raises(exceptions.ApiException):
            gen_object_with_cleanup(
                file_bindings.PublicationsFileApi,
                {"repository_version": repo.latest_version_href, "checkpoint": True},
            )
