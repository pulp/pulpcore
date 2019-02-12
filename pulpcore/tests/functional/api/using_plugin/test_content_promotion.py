# coding=utf-8
"""Tests related to content promotion."""
import hashlib
import unittest
from urllib.parse import urljoin

from pulp_smash import api, config
from pulp_smash.pulp3.constants import DISTRIBUTION_PATH, REPO_PATH
from pulp_smash.pulp3.utils import (
    gen_distribution,
    gen_publisher,
    gen_remote,
    gen_repo,
    get_added_content,
    publish,
    sync,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_PUBLISHER_PATH,
    FILE_REMOTE_PATH
)
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule
)


class ContentPromotionTestCase(unittest.TestCase):
    """Test content promotion."""

    def test_all(self):
        """Test content promotion for a distribution.

        This test targets the following issue:

        * `Pulp #4186 <https://pulp.plan.io/issues/4186>`_

        Do the following:

        1. Create a repository that has at least one repository version.
        2. Create a publisher, and publication.
        3. Create 2 distributions - using the same publication. Those
           distributions will have different ``base_path``.
        4. Assert that distributions have the same publication.
        5. Select a content unit. Download that content unit from Pulp using
           the two different distributions.
           Assert that content unit has the same checksum when fetched from
           different distributions.
        """
        cfg = config.get_config()
        client = api.Client(cfg, api.json_handler)

        repo = client.post(REPO_PATH, gen_repo())
        self.addCleanup(client.delete, repo['_href'])

        remote = client.post(
            FILE_REMOTE_PATH,
            gen_remote(FILE_FIXTURE_MANIFEST_URL)
        )
        self.addCleanup(client.delete, remote['_href'])

        sync(cfg, remote, repo)
        repo = client.get(repo['_href'])

        publisher = client.post(FILE_PUBLISHER_PATH, gen_publisher())
        self.addCleanup(client.delete, publisher['_href'])

        publication = publish(cfg, publisher, repo)
        self.addCleanup(client.delete, publication['_href'])

        distributions = []
        for _ in range(2):
            body = gen_distribution()
            body['publication'] = publication['_href']
            response_dict = client.post(DISTRIBUTION_PATH, body)
            dist_task = client.get(response_dict['task'])
            distribution_href = dist_task['created_resources'][0]
            distribution = client.get(distribution_href)
            distributions.append(distribution)
            self.addCleanup(client.delete, distribution['_href'])

        self.assertEqual(
            distributions[0]['publication'],
            distributions[1]['publication'],
            distributions
        )

        unit_urls = []
        unit_path = get_added_content(repo)[FILE_CONTENT_NAME][0]['relative_path']
        for distribution in distributions:
            unit_url = cfg.get_hosts('api')[0].roles['api']['scheme']
            unit_url += '://' + distribution['base_url'] + '/'
            unit_urls.append(urljoin(unit_url, unit_path))

        client.response_handler = api.safe_handler
        self.assertEqual(
            hashlib.sha256(client.get(unit_urls[0]).content).hexdigest(),
            hashlib.sha256(client.get(unit_urls[1]).content).hexdigest(),
            unit_urls,
        )
