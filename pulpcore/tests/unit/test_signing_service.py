import os

import pytest

from pulpcore.app.models.content import AsciiArmoredDetachedSigningService


@pytest.fixture
def signing_service(tmp_path):
    """A signing service whose script reports the fingerprint and env vars it was invoked with."""
    script = tmp_path / "echo_env.sh"
    script.write_text(
        '#!/bin/sh\nprintf \'{"fingerprint": "%s", "extra": "%s"}\''
        ' "$PULP_SIGNING_KEY_FINGERPRINT" "$EXTRA"\n'
    )
    script.chmod(0o755)
    return AsciiArmoredDetachedSigningService(
        name="echo-env",
        public_key="public-key",
        pubkey_fingerprint="SERVICE_KEY",
        script=str(script),
    )


def test_sign_defaults_to_service_key(signing_service):
    assert signing_service.sign(os.devnull)["fingerprint"] == "SERVICE_KEY"


def test_sign_override_replaces_key_and_keeps_env_vars(signing_service):
    return_value = signing_service.sign(
        os.devnull, env_vars={"EXTRA": "kept"}, pubkey_fingerprint="OTHER_KEY"
    )
    assert return_value == {"fingerprint": "OTHER_KEY", "extra": "kept"}


@pytest.mark.asyncio
async def test_asign_override_replaces_key(signing_service):
    return_value = await signing_service.asign(os.devnull, pubkey_fingerprint="OTHER_KEY")
    assert return_value["fingerprint"] == "OTHER_KEY"
