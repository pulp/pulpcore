import requests

from django.conf import settings

from hashlib import sha256
from pulp_smash import utils


OBJECT_STORAGES = (
    "storages.backends.s3boto3.S3Boto3Storage",
    "storages.backends.azure_storage.AzureStorage",
)


def test_artifact_distribution(cli_client, random_artifact):
    artifact_uuid = random_artifact.pulp_href.split("/")[-2]

    artifact_url = utils.execute_pulpcore_python(
        cli_client,
        "from pulpcore.app.models import Artifact;"
        "from pulpcore.app.util import get_artifact_url;"
        f"print(get_artifact_url(Artifact.objects.get(pk='{artifact_uuid}')));",
    )

    response = requests.get(artifact_url)
    response.raise_for_status()
    hasher = sha256()
    hasher.update(response.content)
    assert hasher.hexdigest() == random_artifact.sha256
    if settings.DEFAULT_FILE_STORAGE in OBJECT_STORAGES:
        content_disposition = response.headers.get("Content-Disposition")
        assert content_disposition is not None
        filename = artifact_uuid
        assert f"attachment;filename={filename}" == content_disposition
