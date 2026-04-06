from pulp_file.app.tasks.synchronizing import _should_optimize_sync


class TestShouldOptimizeSync:
    """Tests for the _should_optimize_sync function."""

    BASE_DETAILS = {
        "url": "http://example.com/PULP_MANIFEST",
        "download_policy": "on_demand",
        "mirror": False,
        "most_recent_version": 1,
        "manifest_checksum": "abc123",
    }

    def _details(self, **overrides):
        d = self.BASE_DETAILS.copy()
        d.update(overrides)
        return d

    def test_no_previous_sync(self):
        """First sync should never be skipped."""
        assert _should_optimize_sync(self._details(), {}) is False

    def test_identical_sync(self):
        """Sync with identical details should be skipped."""
        assert _should_optimize_sync(self._details(), self._details()) is True

    def test_manifest_checksum_changed(self):
        """Sync should not be skipped if the manifest checksum changed."""
        last = self._details()
        current = self._details(manifest_checksum="def456")
        assert _should_optimize_sync(current, last) is False

    def test_url_changed(self):
        """Sync should not be skipped if the remote URL changed."""
        last = self._details()
        current = self._details(url="http://other.com/PULP_MANIFEST")
        assert _should_optimize_sync(current, last) is False

    def test_repository_modified(self):
        """Sync should not be skipped if the repository was modified since last sync."""
        last = self._details(most_recent_version=1)
        current = self._details(most_recent_version=2)
        assert _should_optimize_sync(current, last) is False

    def test_download_policy_to_immediate(self):
        """Sync should not be skipped when switching from deferred to immediate."""
        last = self._details(download_policy="on_demand")
        current = self._details(download_policy="immediate")
        assert _should_optimize_sync(current, last) is False

    def test_download_policy_immediate_to_on_demand(self):
        """Switching from immediate to on_demand does not require re-sync."""
        last = self._details(download_policy="immediate")
        current = self._details(download_policy="on_demand")
        assert _should_optimize_sync(current, last) is True

    def test_download_policy_stays_immediate(self):
        """Staying on immediate should allow optimization."""
        last = self._details(download_policy="immediate")
        current = self._details(download_policy="immediate")
        assert _should_optimize_sync(current, last) is True

    def test_mirror_enabled(self):
        """Sync should not be skipped when switching to mirror mode."""
        last = self._details(mirror=False)
        current = self._details(mirror=True)
        assert _should_optimize_sync(current, last) is False

    def test_mirror_disabled(self):
        """Switching from mirror to additive does not require re-sync."""
        last = self._details(mirror=True)
        current = self._details(mirror=False)
        assert _should_optimize_sync(current, last) is True

    def test_mirror_stays_true(self):
        """Staying in mirror mode should allow optimization."""
        last = self._details(mirror=True)
        current = self._details(mirror=True)
        assert _should_optimize_sync(current, last) is True
