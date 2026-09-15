from types import SimpleNamespace

from pulpcore.app.tasks.replica import _build_remote_settings


def _server(**overrides):
    base = {
        "ca_cert": "api-ca",
        "tls_validation": True,
        "client_cert": "api-cert",
        "client_key": "api-key",
        "download_concurrency": 10,
        "max_retries": 3,
        "total_timeout": 30,
        "connect_timeout": 5,
        "sock_connect_timeout": 5,
        "sock_read_timeout": 5,
        "remote_policy": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_remote_settings_omits_policy_when_unset():
    settings = _build_remote_settings(_server())

    assert "policy" not in settings
    assert settings["ca_cert"] == "api-ca"
    assert settings["download_concurrency"] == 10


def test_build_remote_settings_includes_policy_when_set():
    settings = _build_remote_settings(_server(remote_policy="on_demand"))

    assert settings["policy"] == "on_demand"
