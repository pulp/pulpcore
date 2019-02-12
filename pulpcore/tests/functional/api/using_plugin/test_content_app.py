# coding=utf-8
"""Tests related to content app."""
import unittest
from urllib.parse import urljoin

from requests import HTTPError

from pulp_smash import api, config
from pulp_smash.pulp3.constants import DISTRIBUTION_PATH, REPO_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    gen_distribution,
    gen_publisher,
    gen_repo,
    get_versions,
    publish,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_PATH,
    FILE_PUBLISHER_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import populate_pulp
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule,
)


class ContentAppTestCase(unittest.TestCase):
    """Test content app."""

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables.

        Add content to Pulp.
        """
        cls.cfg = config.get_config()
        delete_orphans(cls.cfg)
        cls.client = api.Client(cls.cfg, api.json_handler)
        populate_pulp(cls.cfg)
        cls.contents = cls.client.get(FILE_CONTENT_PATH)['results'][:2]

    def test_content_app_returns_404(self):
        """Test that content app returns 404 on wrong url.

        This test targets the following issue: 4278

        * `<https://pulp.plan.io/issues/4278>`_

        Do the following:

        1. Create a repository that has at least one repository version.
        2. Create a publisher.
        3. Create a distribution and set the repository and publisher to the
           previous created ones.
        4. Create a publication using the latest repository version.
        5. Verify that the content app serves 404 responses.
        """
        self.assertGreaterEqual(len(self.contents), 2, self.contents)

        # Create a repository.
        repo = self.client.post(REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['_href'])
        self.client.post(
            repo['_versions_href'],
            {'add_content_units': [self.contents[0]['_href']]}
        )
        repo = self.client.get(repo['_href'])

        # Create publisher.
        publisher = self.client.post(FILE_PUBLISHER_PATH, gen_publisher())
        self.addCleanup(self.client.delete, publisher['_href'])

        # Create a distribution
        body = gen_distribution()
        body['repository'] = repo['_href']
        body['publisher'] = publisher['_href']

        response_dict = self.client.post(DISTRIBUTION_PATH, body)
        dist_task = self.client.get(response_dict['task'])
        distribution_href = dist_task['created_resources'][0]
        distribution = self.client.get(distribution_href)
        self.addCleanup(self.client.delete, distribution['_href'])

        last_version_href = get_versions(repo)[-1]['_href']
        publication = publish(self.cfg, publisher, repo, last_version_href)

        self.addCleanup(self.client.delete, publication['_href'])
        distribution = self.client.get(distribution['_href'])

        # Verify 404 response for wrong url of the distribution
        unit_path = 'i-do-not-exist'
        unit_url = self.cfg.get_hosts('api')[0].roles['api']['scheme']
        unit_url += '://' + distribution['base_url'] + '-WRONG/'
        unit_url = urljoin(unit_url, unit_path)

        self.client.response_handler = api.safe_handler
        with self.assertRaisesRegex(HTTPError, r'^404'):
            self.client.get(unit_url).content

        # Verify 404 response for wrong url inside the distribution
        unit_path = 'i-do-not-exist'
        unit_url = self.cfg.get_hosts('api')[0].roles['api']['scheme']
        unit_url += '://' + distribution['base_url'] + '/'
        unit_url = urljoin(unit_url, unit_path)

        self.client.response_handler = api.safe_handler
        with self.assertRaisesRegex(HTTPError, r'^404'):
            self.client.get(unit_url).content
