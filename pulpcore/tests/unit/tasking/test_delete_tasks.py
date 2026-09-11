"""Unit tests for ProtectedError handling in the generic delete tasks."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from asgiref.sync import async_to_sync
from django.db.models.deletion import ProtectedError

from pulpcore.app.tasks import base
from pulpcore.exceptions import ProtectedResourceError


def _patch_plugin_config(monkeypatch, instance):
    """Make the delete tasks resolve to a model whose .get() returns `instance`."""
    serializer_class = MagicMock()
    serializer_class.Meta.model.objects.get.return_value = instance
    serializer_class.Meta.model.objects.aget = AsyncMock(return_value=instance)
    plugin_config = MagicMock()
    plugin_config.named_serializers = {"FakeSerializer": serializer_class}
    monkeypatch.setattr(base, "get_plugin_config", lambda app_label: plugin_config)


@pytest.mark.django_db
def test_general_delete_wraps_protected_error(monkeypatch):
    instance = MagicMock()
    instance.delete.side_effect = ProtectedError("still referenced", set())
    _patch_plugin_config(monkeypatch, instance)

    with pytest.raises(ProtectedResourceError):
        base.general_delete("some-pk", "core", "FakeSerializer")


@pytest.mark.django_db
def test_general_multi_delete_wraps_protected_error(monkeypatch):
    instance = MagicMock()
    instance.delete.side_effect = ProtectedError("still referenced", set())
    _patch_plugin_config(monkeypatch, instance)

    with pytest.raises(ProtectedResourceError):
        base.general_multi_delete([("some-pk", "core", "FakeSerializer")])


@pytest.mark.django_db
def test_ageneral_delete_wraps_protected_error(monkeypatch):
    instance = MagicMock()
    instance.adelete = AsyncMock(side_effect=ProtectedError("still referenced", set()))
    _patch_plugin_config(monkeypatch, instance)

    with pytest.raises(ProtectedResourceError):
        async_to_sync(base.ageneral_delete)("some-pk", "core", "FakeSerializer")
