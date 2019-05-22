# coding=utf-8
"""Tests that perform actions over distributions."""
import unittest

from pulp_smash import api, config, utils
from pulp_smash.pulp3.constants import REPO_PATH
from pulp_smash.pulp3.utils import (
    gen_distribution,
    gen_repo,
    get_versions,
    sync,
)

from requests.exceptions import HTTPError

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_DISTRIBUTION_PATH,
    FILE_REMOTE_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import (
    create_file_publication,
    gen_file_remote,
    skip_if,
)
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class CRUDPublicationDistributionTestCase(unittest.TestCase):
    """CRUD Publication Distribution.

    This test targets the following issue:

    * `Pulp #4839 <https://pulp.plan.io/issues/4839>`_
    * `Pulp #4862 <https://pulp.plan.io/issues/4862>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        cls.attr = ('name', 'base_path',)
        cls.distribution = {}
        cls.publication = {}
        cls.remote = {}
        cls.repo = {}

    @classmethod
    def tearDownClass(cls):
        """Clean class-wide variables."""
        for resource in (cls.publication, cls.remote, cls.repo):
            if resource:
                cls.client.delete(resource['_href'])

    def test_01_create(self):
        """Create a publication distribution.

        Do the following:

        1. Create a repository and 3 repository versions with at least 1 file
           content in it. Create a publication using the second repository
           version.
        2. Create a distribution with 'publication' field set to
           the publication from step (1).
        3. Assert the distribution got created correctly with the correct
           base_path, name, and publication. Assert that content guard is
           unset.
        4. Assert that publication has a 'distributions' reference to the
           distribution (it's backref).

        """
        self.repo.update(self.client.post(REPO_PATH, gen_repo()))
        self.remote.update(
            self.client.post(FILE_REMOTE_PATH, gen_file_remote())
        )
        # create 3 repository versions
        for _ in range(3):
            sync(self.cfg, self.remote, self.repo)
        self.repo = self.client.get(self.repo['_href'])

        versions = get_versions(self.repo)

        self.publication.update(create_file_publication(
            self.cfg,
            self.repo,
            versions[1]['_href']
        ))

        self.distribution.update(
            self.client.post(
                FILE_DISTRIBUTION_PATH,
                gen_distribution(publication=self.publication['_href'])
            )
        )

        self.publication = self.client.get(self.publication['_href'])

        # content_guard is the only parameter unset.
        for key, val in self.distribution.items():
            if key == 'content_guard':
                self.assertIsNone(val, self.distribution)
            else:
                self.assertIsNotNone(val, self.distribution)

        self.assertEqual(
            self.distribution['publication'],
            self.publication['_href'],
            self.distribution
        )

        self.assertEqual(
            self.publication['distributions'][0],
            self.distribution['_href'],
            self.publication
        )

    @skip_if(bool, 'distribution', False)
    def test_02_read(self):
        """Read distribution by its href."""
        distribution = self.client.get(self.distribution['_href'])
        for key, val in self.distribution.items():
            with self.subTest(key=key):
                self.assertEqual(distribution[key], val)

    @skip_if(bool, 'distribution', False)
    def test_03_partially_update(self):
        """Update a distribution using PATCH."""
        for key in self.attr:
            with self.subTest(key=key):
                self.do_partially_update_attr(key)

    @skip_if(bool, 'distribution', False)
    def test_03_fully_update(self):
        """Update a distribution using PUT."""
        for key in self.attr:
            with self.subTest(key=key):
                self.do_fully_update_attr(key)

    @skip_if(bool, 'distribution', False)
    def test_04_delete_distribution(self):
        """Delete a distribution."""
        self.client.delete(self.distribution['_href'])
        with self.assertRaises(HTTPError):
            self.client.get(self.distribution['_href'])

    def do_fully_update_attr(self, attr):
        """Update a distribution attribute using HTTP PUT.

        :param attr: The name of the attribute to update.
        """
        distribution = self.client.get(self.distribution['_href'])
        string = utils.uuid4()
        distribution[attr] = string
        self.client.put(distribution['_href'], distribution)

        # verify the update
        distribution = self.client.get(distribution['_href'])
        self.assertEqual(string, distribution[attr], distribution)

    def do_partially_update_attr(self, attr):
        """Update a distribution using HTTP PATCH.

        :param attr: The name of the attribute to update.
        """
        string = utils.uuid4()
        self.client.patch(self.distribution['_href'], {attr: string})

        # Verify the update
        distribution = self.client.get(self.distribution['_href'])
        self.assertEqual(string, distribution[attr], self.distribution)
