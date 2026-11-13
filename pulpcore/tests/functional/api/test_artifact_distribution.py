import subprocess
from hashlib import sha256

import requests


def test_artifact_distribution(random_artifact):
    """Check artifact delivery and byte ranges through the configured serving path."""
    artifact_uuid = random_artifact.pulp_href.split("/")[-2]

    commands = (
        "from pulpcore.app.models import Artifact;"
        "from pulpcore.app.util import get_artifact_url, get_direct_storage_url;"
        f"artifact = Artifact.objects.get(pk='{artifact_uuid}');"
        "headers = {'Content-Disposition': f'attachment;filename={artifact.pk}'};"
        "print(get_artifact_url(artifact));"
        "print(get_direct_storage_url(artifact.file, headers=headers, "
        "domain=artifact.pulp_domain) is not None);"
    )
    process = subprocess.run(["pulpcore-manager", "shell", "-c", commands], capture_output=True)
    assert process.returncode == 0
    artifact_url, has_direct_storage_url = process.stdout.decode().splitlines()

    response = requests.get(artifact_url)
    response.raise_for_status()
    hasher = sha256()
    hasher.update(response.content)
    assert hasher.hexdigest() == random_artifact.sha256
    if has_direct_storage_url == "True":
        content_disposition = response.headers.get("Content-Disposition")
        assert content_disposition is not None
        filename = artifact_uuid
        assert f"attachment;filename={filename}" == content_disposition

    # This URL is preauthenticated for content-app delivery or signed for object storage,
    # depending on the Domain's configured serving path.
    ranged = requests.get(artifact_url, headers={"Range": "bytes=1-3"})
    ranged.raise_for_status()
    assert ranged.status_code == 206
    assert ranged.content == response.content[1:4]
    assert ranged.headers["Content-Range"] == f"bytes 1-3/{len(response.content)}"
