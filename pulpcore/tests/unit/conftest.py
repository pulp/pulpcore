import pytest
from uuid import uuid4

from pulpcore.app.models import Domain
from pulpcore.app.util import set_domain


@pytest.fixture
def fake_domain():
    """A fixture to prevent `get_domain` to call out to the database."""
    set_domain(Domain(pk=uuid4(), name=uuid4()))
