import os
from types import SimpleNamespace

from pulpcore.app.tasks import replica
from pulpcore.app.tasks.replica import _ssl_temp_files


def test_ssl_temp_files_keep_all_certs_until_context_exits(tmp_path, monkeypatch):
    """Katello replicate() sends ca_cert + client_cert + client_key together.

    The old loop stored only filenames, so the CA NamedTemporaryFile was
    garbage-collected (and unlinked) before pulp-glue opened it.
    """
    monkeypatch.chdir(tmp_path)
    server = SimpleNamespace(
        ca_cert="-----BEGIN CA-----\nca\n-----END CA-----",
        client_cert="-----BEGIN CERT-----\ncert\n-----END CERT-----",
        client_key="-----BEGIN KEY-----\nkey\n-----END KEY-----",
    )

    with _ssl_temp_files(server) as ssl_files:
        for key, expected in (
            ("ca_cert", server.ca_cert),
            ("client_cert", server.client_cert),
            ("client_key", server.client_key),
        ):
            path = ssl_files[key]
            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                assert f.read() == expected
        ca_path = ssl_files["ca_cert"]
        cert_path = ssl_files["client_cert"]
        key_path = ssl_files["client_key"]

    assert not os.path.exists(ca_path)
    assert not os.path.exists(cert_path)
    assert not os.path.exists(key_path)


def test_ssl_temp_files_skips_missing_material(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    server = SimpleNamespace(ca_cert="ca", client_cert=None, client_key=None)

    with _ssl_temp_files(server) as ssl_files:
        assert set(ssl_files) == {"ca_cert"}
        assert os.path.exists(ssl_files["ca_cert"])


def test_replicate_distributions_passes_ca_path_as_verify_ssl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}
    server = SimpleNamespace(
        base_url="https://example.com",
        api_root="/pulp/",
        domain="default",
        username="user",
        password="pass",
        ca_cert="ca",
        client_cert="cert",
        client_key="key",
        tls_validation=True,
        download_concurrency=10,
        max_retries=3,
        total_timeout=30,
        connect_timeout=5,
        sock_connect_timeout=5,
        sock_read_timeout=5,
        q_select=None,
        pulp_domain_id="domain-id",
        pk="server-pk",
    )

    class DummyContext:
        def has_plugin(self, req):
            assert os.path.exists(captured["config"]["verify_ssl"])
            assert os.path.exists(captured["config"]["cert"])
            assert os.path.exists(captured["config"]["key"])
            return False

    class DummyReplicator:
        required_version = ">=0"

    def fake_from_config(config):
        captured["config"] = config
        assert os.path.exists(config["verify_ssl"])
        assert os.path.exists(config["cert"])
        assert os.path.exists(config["key"])
        return DummyContext()

    monkeypatch.setattr(replica.UpstreamPulp.objects, "get", lambda pk: server)
    monkeypatch.setattr(replica.ReplicaContext, "from_config", fake_from_config)
    monkeypatch.setattr(
        replica,
        "pulp_plugin_configs",
        lambda: [SimpleNamespace(label="core", replicator_classes=[DummyReplicator])],
    )
    monkeypatch.setattr(replica.TaskGroup, "current", lambda: "task-group")
    monkeypatch.setattr(replica, "dispatch", lambda *args, **kwargs: None)

    replica.replicate_distributions(server.pk)

    assert isinstance(captured["config"]["verify_ssl"], str)


def test_replicate_distributions_uses_false_verify_ssl_when_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}
    server = SimpleNamespace(
        base_url="https://example.com",
        api_root="/pulp/",
        domain="default",
        username="user",
        password="pass",
        ca_cert="ca",
        client_cert="cert",
        client_key="key",
        tls_validation=False,
        download_concurrency=10,
        max_retries=3,
        total_timeout=30,
        connect_timeout=5,
        sock_connect_timeout=5,
        sock_read_timeout=5,
        q_select=None,
        pulp_domain_id="domain-id",
        pk="server-pk",
    )

    class DummyContext:
        def has_plugin(self, req):
            return False

    class DummyReplicator:
        required_version = ">=0"

    def fake_from_config(config):
        captured["config"] = config
        assert config["verify_ssl"] is False
        assert os.path.exists(config["cert"])
        assert os.path.exists(config["key"])
        return DummyContext()

    monkeypatch.setattr(replica.UpstreamPulp.objects, "get", lambda pk: server)
    monkeypatch.setattr(replica.ReplicaContext, "from_config", fake_from_config)
    monkeypatch.setattr(
        replica,
        "pulp_plugin_configs",
        lambda: [SimpleNamespace(label="core", replicator_classes=[DummyReplicator])],
    )
    monkeypatch.setattr(replica.TaskGroup, "current", lambda: "task-group")
    monkeypatch.setattr(replica, "dispatch", lambda *args, **kwargs: None)

    replica.replicate_distributions(server.pk)

    assert captured["config"]["verify_ssl"] is False
