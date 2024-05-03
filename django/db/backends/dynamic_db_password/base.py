from django.db.backends.postgresql import base
from logging import getLogger

from azure import identity

TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

logger = getLogger(__name__)

class DatabaseWrapper(base.DatabaseWrapper):
    """
    Dynamically get a bearer token from azure identity for the db password.
    Mostly pulled from https://stackoverflow.com/a/75588453
    """
    default_credential = identity.DefaultAzureCredential()

    def get_connection_params(self):
        params = super().get_connection_params()
        logger.debug("Initializing connection to database in dynamic_db_password.")
        # If a password is set, just use it (dev environments)
        if 'password' not in params:
            logger.info("Fetching bearer token for database password")
            # Else fetch a token from azure identity
            token = self.default_credential.get_token(TOKEN_SCOPE)
            params['password'] = token.token

        return params
