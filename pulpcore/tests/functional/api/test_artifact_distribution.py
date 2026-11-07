import subprocess
from hashlib import sha256

import requests

from pulpcore.app.storage_backends import backend_id
from pulpcore.constants import STORAGE_BACKENDS

OBJECT_STORAGES = {STORAGE_BACKENDS.S3, STORAGE_BACKENDS.AZURE, STORAGE_BACKENDS.GCS}


def test_artifact_distribution(random_artifact, pulp_settings):
    settings = pulp_settings
    artifact_uuid = random_artifact.pulp_href.split("/")[-2]

    commands = (
        "from pulpcore.app.models import Artifact;"
        "from pulpcore.app.util import get_artifact_url;"
        f"print(get_artifact_url(Artifact.objects.get(pk='{artifact_uuid}')));"
    )
    process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)
    assert process.returncode == 0
    artifact_url = process.stdout.decode().strip()

    response = requests.get(artifact_url)
    response.raise_for_status()
    hasher = sha256()
    hasher.update(response.content)
    assert hasher.hexdigest() == random_artifact.sha256
    if backend_id(settings.STORAGES["default"]["BACKEND"]) in OBJECT_STORAGES:
        content_disposition = response.headers.get("Content-Disposition")
        assert content_disposition is not None
        filename = artifact_uuid
        assert f"attachment;filename={filename}" == content_disposition
    else:
        ranged = requests.get(artifact_url, headers={"Range": "bytes=1-3"})
        ranged.raise_for_status()
        assert ranged.status_code == 206
        assert ranged.content == response.content[1:4]
        assert ranged.headers["Content-Range"] == f"bytes 1-3/{len(response.content)}"
