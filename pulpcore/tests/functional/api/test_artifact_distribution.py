import requests
from hashlib import sha256
from pulp_smash import utils


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
