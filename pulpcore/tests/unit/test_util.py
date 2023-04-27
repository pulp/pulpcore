import pytest
from unittest import mock

from pulpcore.app import models, util


pytestmark = pytest.mark.usefixtures("fake_domain")


def test_get_view_name_for_model_with_object():
    """
    Use Repository as an example that should work.
    """
    ret = util.get_view_name_for_model(models.Artifact(), "foo")
    assert ret == "artifacts-foo"


def test_get_view_name_for_model_with_model():
    """
    Use Repository as an example that should work.
    """
    ret = util.get_view_name_for_model(models.Artifact, "foo")
    assert ret == "artifacts-foo"


def test_get_view_name_for_model_not_found(monkeypatch):
    """
    Given an unknown viewset (in this case a Mock()), this should raise LookupError.
    """
    monkeypatch.setattr(util, "get_viewset_for_model", mock.Mock())
    with pytest.raises(LookupError):
        util.get_view_name_for_model(mock.Mock(), "foo")
