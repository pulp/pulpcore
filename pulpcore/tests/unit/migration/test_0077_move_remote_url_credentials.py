import pytest
from unittest.mock import Mock

from pulpcore.app.models import Remote
from pulpcore.app import migrations


@pytest.mark.django_db
def test_move_remote_url_credentials():
    """Test the move remote url credentials migration."""
    remote = Remote.objects.create(
        name="test-url", url="http://elladan:lembas-EXAMPLE@rivendell.org", pulp_type="file"
    )
    remote_without_credentials = Remote.objects.create(
        name="test-url-no-credentials",
        url="https://download.copr.fedorainfracloud.org/results/@caddy/caddy/epel-8-x86_64/",
        pulp_type="file",
    )

    apps_mock = Mock()
    apps_mock.get_model.return_value = Remote

    migration = getattr(migrations, "0077_move_remote_url_credentials")
    migration.move_remote_url_credentials(apps_mock, None)

    remote = Remote.objects.get(name="test-url")
    assert remote.url == "http://rivendell.org"
    assert remote.username == "elladan"
    assert remote.password == "lembas-EXAMPLE"

    remote_without_credentials = Remote.objects.get(name="test-url-no-credentials")
    assert (
        remote_without_credentials.url
        == "https://download.copr.fedorainfracloud.org/results/@caddy/caddy/epel-8-x86_64/"
    )
