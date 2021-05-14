"""Tests related to content promotion."""
import hashlib
import unittest
from urllib.parse import urljoin

from pulp_smash import api, config
from pulp_smash.pulp3.utils import gen_distribution, gen_remote, gen_repo, get_added_content, sync

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_DISTRIBUTION_PATH,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_REMOTE_PATH,
    FILE_REPO_PATH,
    PULP_CONTENT_BASE_URL,
)
from pulpcore.tests.functional.api.using_plugin.utils import create_file_publication
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class ContentPromotionTestCase(unittest.TestCase):
    """Test content promotion."""

    def test_all(self):
        """Test content promotion for a distribution.

        This test targets the following issue:

        * `Pulp #4186 <https://pulp.plan.io/issues/4186>`_
        * `Pulp #8475 <https://pulp.plan.io/issues/8475>`_
        * `Pulp #8760 <https://pulp.plan.io/issues/8760>`_

        Do the following:

        1. Create a repository that has at least one repository version.
        2. Create a publication.
        3. Create 2 distributions - using the same publication. Those
           distributions will have different ``base_path``.
        4. Assert that distributions have the same publication.
        5. Create another distribution using same repository version.
        5. Assert that distributions are viewable from base url
        6. Assert that content in distributions are viewable
        7. Select a content unit. Download that content unit from Pulp using
           the three different distributions.
           Assert that content unit has the same checksum when fetched from
           different distributions.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(FILE_REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo["pulp_href"])

        remote = client.post(FILE_REMOTE_PATH, gen_remote(FILE_FIXTURE_MANIFEST_URL))
        self.addCleanup(client.delete, remote["pulp_href"])

        sync(cfg, remote, repo)
        repo = client.get(repo["pulp_href"])

        publication = create_file_publication(cfg, repo)
        self.addCleanup(client.delete, publication["pulp_href"])

        distributions = []
        for _ in range(2):
            body = gen_distribution()
            body["publication"] = publication["pulp_href"]
            distribution = client.using_handler(api.task_handler).post(FILE_DISTRIBUTION_PATH, body)
            distributions.append(distribution)
            self.addCleanup(client.delete, distribution["pulp_href"])

        self.assertEqual(
            distributions[0]["publication"], distributions[1]["publication"], distributions
        )

        body = gen_distribution()
        body["repository"] = repo["pulp_href"]
        distribution = client.using_handler(api.task_handler).post(FILE_DISTRIBUTION_PATH, body)
        distributions.append(distribution)
        self.addCleanup(client.delete, distribution["pulp_href"])

        client.response_handler = api.safe_handler
        self.assertEqual(client.get(PULP_CONTENT_BASE_URL).status_code, 200)

        for distribution in distributions:
            self.assertEqual(client.get(distribution["base_url"]).status_code, 200)

        unit_urls = []
        unit_path = get_added_content(repo)[FILE_CONTENT_NAME][0]["relative_path"]
        for distribution in distributions:
            unit_url = distribution["base_url"]
            unit_urls.append(urljoin(unit_url, unit_path))

        self.assertEqual(
            hashlib.sha256(client.get(unit_urls[0]).content).hexdigest(),
            hashlib.sha256(client.get(unit_urls[1]).content).hexdigest(),
            unit_urls,
        )
        self.assertEqual(
            hashlib.sha256(client.get(unit_urls[0]).content).hexdigest(),
            hashlib.sha256(client.get(unit_urls[2]).content).hexdigest(),
            unit_urls,
        )
