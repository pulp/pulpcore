import pytest

from rest_framework.serializers import ValidationError

import pulpcore.app.apps
from pulpcore.app.tasks.importer import _check_versions


def _pulp_plugin_configs():
    for _label, _version in [("123", "1.2.3"), ("215", "2.1.5")]:

        class _AppConfigMock:
            label = _label
            version = _version  # Every component is vers 1.2.3

        yield _AppConfigMock


def test_vers_check(monkeypatch):
    monkeypatch.setattr(pulpcore.app.apps, "pulp_plugin_configs", _pulp_plugin_configs)
    export_json = [{"component": "123", "version": "1.2.3"}]
    _check_versions(export_json)

    export_json = [{"component": "123", "version": "1.2"}]
    _check_versions(export_json)

    export_json = [{"component": "123", "version": "1.2.7"}]
    _check_versions(export_json)

    export_json = [
        {"component": "123", "version": "1.2.0"},
        {"component": "215", "version": "2.1.9"},
    ]
    _check_versions(export_json)

    export_json = [{"component": "123", "version": "1.4.3"}]
    with pytest.raises(ValidationError):
        _check_versions(export_json)

    export_json = [{"component": "123", "version": "2.2.3"}]
    with pytest.raises(ValidationError):
        _check_versions(export_json)

    export_json = [{"component": "non_existent", "version": "1.2.3"}]
    with pytest.raises(ValidationError):
        _check_versions(export_json)

    export_json = [
        {"component": "123", "version": "1.2.3"},
        {"component": "non_existent", "version": "1.2.3"},
    ]
    with pytest.raises(ValidationError):
        _check_versions(export_json)
