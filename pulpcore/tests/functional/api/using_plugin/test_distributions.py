# coding=utf-8
"""Tests that perform actions over distributions."""
import unittest

from pulp_smash import api, config, utils
from pulp_smash.pulp3.utils import gen_distribution

from pulpcore.tests.functional.api.using_plugin.constants import (
    FILE_DISTRIBUTION_PATH,
)
from pulpcore.tests.functional.api.using_plugin.utils import skip_if
from pulpcore.tests.functional.api.using_plugin.utils import set_up_module as setUpModule  # noqa


class CRUDPublicationDistributionTestCase(unittest.TestCase):
    """CRUD Publication Distribution.

    This test targets the following issue:

    `Pulp #4862 <https://pulp.plan.io/issues/4862>`_
    """

    @classmethod
    def setUpClass(cls):
        """Create class-wide variables."""
        cls.cfg = config.get_config()
        cls.client = api.Client(cls.cfg)
        cls.distribution = {}
        cls.attr = ('name', 'base_path',)

    def test_01_create(self):
        """Create a publication distribution."""
        self.distribution.update(
            self.client.post(FILE_DISTRIBUTION_PATH, gen_distribution())
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
        """Update a distribution using HTTP patch.

        :param attr: The name of the attribute to update.
        """
        string = utils.uuid4()
        self.client.patch(self.distribution['_href'], {attr: string})

        # Verify the update
        distribution = self.client.get(self.distribution['_href'])
        self.assertEqual(string, distribution[attr], self.distribution)
