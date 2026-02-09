"""Unit tests for Git sync helper functions."""

import os

from unittest import mock

from pulp_file.app.tasks.synchronizing import _build_clone_url, _build_clone_env


class TestBuildCloneUrl:
    """Tests for _build_clone_url."""

    @staticmethod
    def _mock_remote(url, username=None, password=None):
        remote = mock.Mock()
        remote.url = url
        remote.username = username
        remote.password = password
        return remote

    def test_url_without_credentials(self):
        remote = self._mock_remote("https://github.com/pulp/pulpcore.git")
        assert _build_clone_url(remote) == "https://github.com/pulp/pulpcore.git"

    def test_https_with_credentials(self):
        remote = self._mock_remote("https://github.com/pulp/pulpcore.git", "user", "p@ssw0rd")
        result = _build_clone_url(remote)
        assert result == "https://user:p@ssw0rd@github.com/pulp/pulpcore.git"

    def test_http_with_credentials(self):
        remote = self._mock_remote("http://git.example.com/repo.git", "user", "pass")
        result = _build_clone_url(remote)
        assert result == "http://user:pass@git.example.com/repo.git"

    def test_ssh_url_credentials_not_embedded(self):
        """SSH URLs should not have credentials embedded."""
        remote = self._mock_remote("git@github.com:pulp/pulpcore.git", "user", "pass")
        result = _build_clone_url(remote)
        assert result == "git@github.com:pulp/pulpcore.git"

    def test_url_with_port_and_credentials(self):
        remote = self._mock_remote("https://git.example.com:8443/repo.git", "user", "pass")
        result = _build_clone_url(remote)
        assert result == "https://user:pass@git.example.com:8443/repo.git"

    def test_username_only_no_embedding(self):
        """Only embed credentials when both username AND password are present."""
        remote = self._mock_remote("https://github.com/pulp/pulpcore.git", "user", None)
        assert _build_clone_url(remote) == "https://github.com/pulp/pulpcore.git"

    def test_password_only_no_embedding(self):
        remote = self._mock_remote("https://github.com/pulp/pulpcore.git", None, "pass")
        assert _build_clone_url(remote) == "https://github.com/pulp/pulpcore.git"

    def test_file_url_no_credentials(self):
        remote = self._mock_remote("file:///tmp/my-repo.git")
        assert _build_clone_url(remote) == "file:///tmp/my-repo.git"

    def test_file_url_credentials_not_embedded(self):
        """file:// URLs should not have credentials embedded."""
        remote = self._mock_remote("file:///tmp/my-repo.git", "user", "pass")
        assert _build_clone_url(remote) == "file:///tmp/my-repo.git"


class TestBuildCloneEnv:
    """Tests for _build_clone_env."""

    @staticmethod
    def _mock_remote(**kwargs):
        remote = mock.Mock()
        remote.proxy_url = kwargs.get("proxy_url", None)
        remote.proxy_username = kwargs.get("proxy_username", None)
        remote.proxy_password = kwargs.get("proxy_password", None)
        remote.tls_validation = kwargs.get("tls_validation", True)
        remote.ca_cert = kwargs.get("ca_cert", None)
        remote.client_cert = kwargs.get("client_cert", None)
        remote.client_key = kwargs.get("client_key", None)
        return remote

    def test_defaults_no_extra_env(self):
        """A remote with default values should not inject extra env vars."""
        remote = self._mock_remote()
        env = _build_clone_env(remote)
        assert "GIT_SSL_NO_VERIFY" not in env
        assert "GIT_SSL_CAINFO" not in env
        assert "GIT_SSL_CERT" not in env
        assert "GIT_SSL_KEY" not in env

    def test_proxy_url(self):
        remote = self._mock_remote(proxy_url="http://proxy.example.com:8080")
        env = _build_clone_env(remote)
        assert env["http_proxy"] == "http://proxy.example.com:8080"
        assert env["https_proxy"] == "http://proxy.example.com:8080"

    def test_proxy_with_auth(self):
        remote = self._mock_remote(
            proxy_url="http://proxy.example.com:8080",
            proxy_username="proxyuser",
            proxy_password="proxypass",
        )
        env = _build_clone_env(remote)
        assert "proxyuser:proxypass@proxy.example.com:8080" in env["http_proxy"]
        assert "proxyuser:proxypass@proxy.example.com:8080" in env["https_proxy"]

    def test_tls_validation_disabled(self):
        remote = self._mock_remote(tls_validation=False)
        env = _build_clone_env(remote)
        assert env["GIT_SSL_NO_VERIFY"] == "true"

    def test_tls_validation_enabled(self):
        remote = self._mock_remote(tls_validation=True)
        env = _build_clone_env(remote)
        assert "GIT_SSL_NO_VERIFY" not in env

    def test_ca_cert_written_to_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ca_pem = "-----BEGIN CERTIFICATE-----\nfakecert\n-----END CERTIFICATE-----"
        remote = self._mock_remote(ca_cert=ca_pem)
        env = _build_clone_env(remote)
        assert "GIT_SSL_CAINFO" in env
        with open(env["GIT_SSL_CAINFO"]) as f:
            assert f.read() == ca_pem
        os.unlink(env["GIT_SSL_CAINFO"])

    def test_client_cert_and_key_written_to_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cert_pem = "-----BEGIN CERTIFICATE-----\nfakecert\n-----END CERTIFICATE-----"
        key_pem = "-----BEGIN RSA PRIVATE KEY-----\nfakekey\n-----END RSA PRIVATE KEY-----"
        remote = self._mock_remote(client_cert=cert_pem, client_key=key_pem)
        env = _build_clone_env(remote)
        assert "GIT_SSL_CERT" in env
        assert "GIT_SSL_KEY" in env
        with open(env["GIT_SSL_CERT"]) as f:
            assert f.read() == cert_pem
        with open(env["GIT_SSL_KEY"]) as f:
            assert f.read() == key_pem
        os.unlink(env["GIT_SSL_CERT"])
        os.unlink(env["GIT_SSL_KEY"])

    def test_inherits_existing_env(self):
        """The returned env should contain the existing process environment."""
        remote = self._mock_remote()
        env = _build_clone_env(remote)
        assert "PATH" in env
