import pytest
from rest_framework.serializers import ValidationError

from pulpcore.download import FileDownloader


@pytest.fixture
def import_paths(settings):
    settings.ALLOWED_IMPORT_PATHS = ["/static", "/var/www"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/www",
        "file:///tmp/www/",
        "file:///tmp/www/a",
        "file:///tmp/www/a/",
    ],
)
def test_file_downloader_accepts_regular_file_urls(url, import_paths):
    FileDownloader(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "...",
        "/",
        "file:///",
        "file:.",
        "file://var/www",
        "file:///../../../../var/www",
        "file:///var/www/../../../../etc/secrets",
        "file:../../../../../../../etc/secrets",
    ],
)
def test_file_downloader_rejects_path_traversal_attempts(url, import_paths):
    with pytest.raises(ValidationError):
        FileDownloader(url)
