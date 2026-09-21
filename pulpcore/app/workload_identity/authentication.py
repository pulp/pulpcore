"""DRF authentication that validates a third-party OIDC token against its provider's JWKS.

The token arrives as a `Bearer` token, or as the password of a `Basic` header whose username
is the reserved workload-identity name. On success its claims map to grants and a stateless
`WorkloadIdentityPrincipal` is returned.
"""

import base64
import binascii
import logging

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from pulpcore.app.workload_identity import config, rules
from pulpcore.app.workload_identity.principal import WorkloadIdentityPrincipal

_logger = logging.getLogger("pulpcore.workload_identity")


class WorkloadIdentityAuthentication(BaseAuthentication):
    """Authenticate requests bearing a third-party OIDC token.

    On success this returns a stateless `WorkloadIdentityPrincipal` whose permissions are
    derived entirely from the grants earned by the token's claims. When the
    request carries no token, or a token that is not meant for us, the
    authenticator returns `None` so that other authenticators may run.
    """

    def _get_token(self, request):
        """Return the token from the Authorization header, or None.

        Accepts a `Bearer` token, or a token carried as the password of a `Basic` header whose
        username is the reserved workload-identity name. Any other `Basic` header is left for the
        regular authenticators.
        """
        header = request.META.get("HTTP_AUTHORIZATION", "")
        parts = header.split()
        if len(parts) != 2:
            return None
        scheme, value = parts
        scheme = scheme.lower()
        if scheme == "bearer":
            return value
        if scheme == "basic":
            try:
                decoded = base64.b64decode(value).decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                return None
            username, sep, password = decoded.partition(":")
            if not sep or username != config.basic_username():
                return None
            return password
        return None

    def authenticate(self, request):
        """Validate the token and return `(principal, claims)`, or `None` if it is not ours."""
        token = self._get_token(request)
        if not token:
            return None

        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        issuer = unverified.get("iss")

        provider = config.provider_for_issuer(issuer)
        if provider is None:
            return None

        try:
            signing_key = config.jwks_client(provider).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=provider.get("algorithms", ["RS256"]),
                issuer=provider["issuer"],
                audience=provider["audience"],
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            _logger.info("Rejecting OIDC token from %s: %s", issuer, exc)
            raise AuthenticationFailed("Invalid OIDC token.")

        grants = rules.grants_for(provider, claims)
        if not grants:
            _logger.info(
                "No matching OIDC rule for sub=%r repository=%r",
                claims.get("sub"),
                claims.get("repository"),
            )
            raise AuthenticationFailed("No matching OIDC rule.")

        return (WorkloadIdentityPrincipal(grants, username=""), claims)

    def authenticate_header(self, request):
        """Return the `WWW-Authenticate` value so failures are 401, not 403."""
        return "Bearer"
