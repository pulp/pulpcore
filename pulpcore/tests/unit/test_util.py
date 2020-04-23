from unittest import TestCase, mock

from pulpcore.app import models, util


class TestViewNameForModel(TestCase):
    def test_repository(self):
        """
        Use Repository as an example that should work.
        """
        ret = util.get_view_name_for_model(models.Artifact(), "foo")
        self.assertEqual(ret, "artifacts-foo")

    @mock.patch.object(util, "get_viewset_for_model")
    def test_not_found(self, mock_viewset_for_model):
        """
        Given an unknown viewset (in this case a Mock()), this should raise LookupError.
        """
        self.assertRaises(LookupError, util.get_view_name_for_model, mock.Mock(), "foo")
