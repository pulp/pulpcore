import pytest

from pulpcore.app.tasks.export import UnexportableArtifactException, _local_path_from_file_url


@pytest.mark.parametrize(
    "url,path",
    [
        ["file:///srv/static/a", "/srv/static/a"],
        ["file:///srv/pub/a", "/srv/pub/a"],
        ["file:///srv/static/a/", "/srv/static/a"],
        ["file:/srv/static/a", "/srv/static/a"],
        ["file:////srv/static/a", "/srv/static/a"],
        ["file://///srv/static/a", "/srv/static/a"],
        ["file:///srv/static/", "/srv/static"],
        ["file:///srv/static/a//b/c", "/srv/static/a/b/c"],
        ["file:///srv/static/a/../b", "/srv/static/b"],
        ["file://localhost/srv/static/a", "/srv/static/a"],
        [
            "file:///srv/static/a/b%2f..%2f..%2fetc/password",
            "/srv/static/a/b%2f..%2f..%2fetc/password",
        ],
        [
            "file:///srv/static/a%2f..%2f..%2f..%2fetc/password",
            "/srv/static/a%2f..%2f..%2f..%2fetc/password",
        ],
    ],
)
def test_local_path_from_file_accepts_proper_urls(settings, url, path):
    settings.ALLOWED_IMPORT_PATHS = ["/srv/static", "/srv/pub"]

    assert _local_path_from_file_url(url) == path


@pytest.mark.parametrize(
    "url",
    [
        "file://srv/static/a",
        "file:///srv/b",
        "file:///srv/b",
        "file:///srv/static/a/../../../etc/password",
    ],
)
def test_local_path_from_file_rejects_improper_urls(settings, url):
    settings.ALLOWED_IMPORT_PATHS = ["/srv/static", "/srv/pub"]

    with pytest.raises(UnexportableArtifactException):
        _local_path_from_file_url(url)
