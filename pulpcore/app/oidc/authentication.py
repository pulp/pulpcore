"""DRF authentication that validates third-party OIDC tokens.

This authenticator accepts an OIDC token issued by a configured third-party
provider (for example a GitHub Actions workflow token), verifies it against the
provider's JWKS, maps its claims to grants and returns a stateless
``OIDCPrincipal``. No database user is involved.

The token may arrive either as a ``Bearer`` token or inside a ``Basic`` header
(the way ``docker login`` passes a token, where the password field carries it).
"""

import base64
import binascii
import logging

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from pulpcore.app.oidc import config, rules
from pulpcore.app.oidc.principal import OIDCPrincipal

_logger = logging.getLogger("pulpcore.oidc")


class OIDCAuthentication(BaseAuthentication):
    """Authenticate requests bearing a third-party OIDC token.

    On success this returns a stateless ``OIDCPrincipal`` whose permissions are
    derived entirely from the grants earned by the token's claims. When the
    request carries no token, or a token that is not meant for us, the
    authenticator returns ``None`` so that other authenticators may run.
    """

    def _get_token(self, request):
        """Return the token from the Authorization header (Bearer, or Basic password), or None."""
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
            if ":" not in decoded:
                return None
            # docker login passes the token as the password; the username is ignored.
            _, _, password = decoded.partition(":")
            return password
        return None

    def authenticate(self, request):
        """Validate an OIDC token and return ``(OIDCPrincipal, claims)``, or ``None`` if not ours."""
        token = self._get_token(request)
        if not token:
            return None

        # Peek at the issuer without verifying the signature. If this is not a
        # JWT at all, it is not meant for us.
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return None
        issuer = unverified.get("iss")

        provider = config.provider_for_issuer(issuer)
        if provider is None:
            return None

        # Verify the token for real against the provider's JWKS.
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

        # The username is intentionally empty: the container registry token
        # subject must be empty for a principal with no database user.
        return (OIDCPrincipal(grants, username=""), claims)

    def authenticate_header(self, request):
        """Return the ``WWW-Authenticate`` value so failures are 401, not 403."""
        return "Bearer"
