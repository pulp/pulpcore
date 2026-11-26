import logging
import uuid

import pytest

from pulpcore.app.models import Artifact
from pulpcore.responses import ArtifactResponse


async def create_artifact(tmp_path):
    tmp_file = tmp_path / str(uuid.uuid4())
    tmp_file.write_text(str(tmp_file))
    artifact = Artifact.init_and_validate(str(tmp_file))
    await artifact.asave()
    return artifact


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_artifact_response_loads_deferred_domain(tmp_path, caplog):
    """
    An Artifact without a preloaded pulp_domain is loaded on demand with a deprecation warning.

    Remove this test when the deprecation is turned into an error.
    """
    artifact = await create_artifact(tmp_path)
    try:
        deferred = await Artifact.objects.aget(pk=artifact.pk)
        assert not Artifact.pulp_domain.is_cached(deferred)

        with caplog.at_level(logging.WARNING, logger="pulpcore.deprecation"):
            storage = await ArtifactResponse(deferred)._get_storage()

        assert storage is not None
        assert Artifact.pulp_domain.is_cached(deferred)
        assert "without a preloaded pulp_domain" in caplog.text
    finally:
        await artifact.adelete()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_artifact_response_preloaded_domain_does_not_warn(tmp_path, caplog):
    """
    An Artifact with a preloaded pulp_domain is used without a deprecation warning.

    Remove this test when the deprecation is turned into an error.
    """
    artifact = await create_artifact(tmp_path)
    try:
        preloaded = await Artifact.objects.select_related("pulp_domain").aget(pk=artifact.pk)

        with caplog.at_level(logging.WARNING, logger="pulpcore.deprecation"):
            storage = await ArtifactResponse(preloaded)._get_storage()

        assert storage is not None
        assert "without a preloaded pulp_domain" not in caplog.text
    finally:
        await artifact.adelete()
