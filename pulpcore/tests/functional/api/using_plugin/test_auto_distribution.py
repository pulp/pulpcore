# coding=utf-8
"""Tests related to auto distributions."""
import hashlib
import unittest
from urllib.parse import urljoin

from requests import HTTPError

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import DISTRIBUTION_PATH, REPO_PATH
from pulp_smash.pulp3.utils import (
    delete_orphans,
    gen_distribution,
    gen_publisher,
    gen_remote,
    gen_repo,
    get_added_content,
    get_versions,
    publish,
    sync,
)

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_CONTENT_NAME,
    FILE_CONTENT_PATH,
    FILE_FIXTURE_MANIFEST_URL,
    FILE_PUBLISHER_PATH,
    FILE_REMOTE_PATH,
    FILE_URL
)
from pulpcore.tests.functional.api.using_plugin.utils import populate_pulp
from pulpcore.tests.functional.api.using_plugin.utils import (  # noqa:F401
    set_up_module as setUpModule
)


class AutoDistributionTestCase(unittest.TestCase):
    """Test auto distribution."""

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

    def test_repo_auto_distribution(self):
        """Test auto distribution of a repository.

        This test targets the following issue:

        * `Pulp Smash #947 <https://github.com/PulpQE/pulp-smash/issues/947>`_

        Do the following:

        1. Create a repository that has at least one repository version.
        2. Create a publisher.
        3. Create a distribution and set the repository and publisher to the
           previous created ones.
        4. Create a publication using the latest repository version.
        5. Assert that the previous distribution has a  ``publication`` set as
           the one created in step 4.
        6. Create a new repository version by adding content to the repository.
        7. Create another publication using the just created repository
           version.
        8. Assert that distribution now has the ``publication`` set to the
           publication created in the step 7.
        9. Verify that content added in the step 7 is now available to download
           from distribution, and verify that the content unit has the same
           checksum when fetched directly from Pulp-Fixtures.
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

        # Assert that distribution was updated as per step 5.
        self.assertEqual(distribution['publication'], publication['_href'])

        # Create a new repository version.
        self.client.post(
            repo['_versions_href'],
            {'add_content_units': [self.contents[1]['_href']]}
        )
        repo = self.client.get(repo['_href'])
        last_version_href = get_versions(repo)[-1]['_href']
        publication = publish(self.cfg, publisher, repo, last_version_href)

        self.addCleanup(self.client.delete, publication['_href'])
        distribution = self.client.get(distribution['_href'])

        # Assert that distribution was updated as per step 8.
        self.assertEqual(distribution['publication'], publication['_href'])
        unit_path = get_added_content(
            repo, last_version_href
        )[FILE_CONTENT_NAME][0]['relative_path']
        unit_url = self.cfg.get_hosts('api')[0].roles['api']['scheme']
        unit_url += '://' + distribution['base_url'] + '/'
        unit_url = urljoin(unit_url, unit_path)

        self.client.response_handler = api.safe_handler
        pulp_hash = hashlib.sha256(
            self.client.get(unit_url).content
        ).hexdigest()
        fixtures_hash = hashlib.sha256(
            utils.http_get(urljoin(FILE_URL, unit_path))
        ).hexdigest()

        # Verify checksum. Step 9.
        self.assertEqual(fixtures_hash, pulp_hash)


class SetupAutoDistributionTestCase(unittest.TestCase):
    """Verify the set up of parameters related to auto distribution."""

    def setUp(self):
        """Create test-wide variables."""
        self.cfg = config.get_config()
        self.client = api.Client(self.cfg, api.json_handler)

    def test_all(self):
        """Verify the set up of parameters related to auto distribution.

        This test targets the following issues:

        * `Pulp #3295 <https://pulp.plan.io/issues/3295>`_
        * `Pulp #3392 <https://pulp.plan.io/issues/3392>`_
        * `Pulp #3394 <https://pulp.plan.io/issues/3394>`_
        * `Pulp #3671 <https://pulp.plan.io/issues/3671>`_
        * `Pulp Smash #883 <https://github.com/PulpQE/pulp-smash/issues/883>`_
        * `Pulp Smash #917 <https://github.com/PulpQE/pulp-smash/issues/917>`_
        """
        # Create a repository and a publisher.
        repo = self.client.post(REPO_PATH, gen_repo())
        self.addCleanup(self.client.delete, repo['_href'])

        publisher = self.client.post(FILE_PUBLISHER_PATH, gen_publisher())
        self.addCleanup(self.client.delete, publisher['_href'])

        # Create a distribution.
        self.try_create_distribution(publisher=publisher['_href'])
        self.try_create_distribution(repository=repo['_href'])
        body = gen_distribution()
        body['publisher'] = publisher['_href']
        body['repository'] = repo['_href']
        response_dict = self.client.post(DISTRIBUTION_PATH, body)
        dist_task = self.client.get(response_dict['task'])
        distribution_href = dist_task['created_resources'][0]
        distribution = self.client.get(distribution_href)
        self.addCleanup(self.client.delete, distribution['_href'])

        # Update the distribution.
        self.try_update_distribution(distribution, publisher=None)
        self.try_update_distribution(distribution, repository=None)
        self.client.patch(distribution['_href'], {
            'publisher': None,
            'repository': None,
        })
        distribution = self.client.get(distribution['_href'])
        self.assertIsNone(distribution['publisher'], distribution)
        self.assertIsNone(distribution['repository'], distribution)

        # Publish the repository. Assert that distribution does not point to
        # the new publication (because publisher and repository are unset).
        remote = self.client.post(
            FILE_REMOTE_PATH,
            gen_remote(FILE_FIXTURE_MANIFEST_URL),
        )
        self.addCleanup(self.client.delete, remote['_href'])

        sync(self.cfg, remote, repo)

        publication = publish(self.cfg, publisher, repo)
        self.addCleanup(self.client.delete, publication['_href'])

        distribution = self.client.get(distribution['_href'])
        self.assertNotEqual(distribution['publication'], publication['_href'])

    def try_create_distribution(self, **kwargs):
        """Unsuccessfully create a distribution.

        Merge the given kwargs into the body of the request.
        """
        body = gen_distribution()
        body.update(kwargs)
        with self.assertRaises(HTTPError):
            self.client.post(DISTRIBUTION_PATH, body)

    def try_update_distribution(self, distribution, **kwargs):
        """Unsuccessfully update a distribution with HTTP PATCH.

        Use the given kwargs as the body of the request.
        """
        with self.assertRaises(HTTPError):
            self.client.patch(distribution['_href'], kwargs)
        distribution = self.client.get(distribution['_href'])
        self.assertIsNotNone(distribution['publisher'], distribution)
        self.assertIsNotNone(distribution['repository'], distribution)
