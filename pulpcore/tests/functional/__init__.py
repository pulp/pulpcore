import uuid

import pytest

from pulpcore.client.pulpcore import (
    ApiClient,
    UsersApi,
    UsersRolesApi,
)


@pytest.fixture(scope="session")
def pulpcore_client(bindings_cfg):
    return ApiClient(bindings_cfg)


@pytest.fixture
def users_api_client(pulpcore_client):
    return UsersApi(pulpcore_client)


@pytest.fixture
def users_roles_api_client(pulpcore_client):
    return UsersRolesApi(pulpcore_client)


@pytest.fixture
def gen_user(bindings_cfg, users_api_client, users_roles_api_client, gen_object_with_cleanup):
    class user_context:
        def __init__(self, username=None, model_roles=None, object_roles=None):
            self.username = username or str(uuid.uuid4())
            self.password = str(uuid.uuid4())
            self.user = gen_object_with_cleanup(
                users_api_client, {"username": self.username, "password": self.password}
            )
            if model_roles:
                for role in model_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "content_object": None},
                    )
            if object_roles:
                for role, content_object in object_roles:
                    users_roles_api_client.create(
                        auth_user_href=self.user.pulp_href,
                        user_role={"role": role, "content_object": content_object},
                    )

        def __enter__(self):
            self.saved_username, self.saved_password = (
                bindings_cfg.username,
                bindings_cfg.password,
            )
            bindings_cfg.username, bindings_cfg.password = self.username, self.password
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            bindings_cfg.username, bindings_cfg.password = (
                self.saved_username,
                self.saved_password,
            )

    return user_context
