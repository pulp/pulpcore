"""Access to the ``OIDC_AUTH`` setting and per-provider JWKS clients."""

import functools

from django.conf import settings
from jwt import PyJWKClient


def config():
    return getattr(settings, "OIDC_AUTH", {}) or {}


def strategy():
    return config().get("strategy", "union")


def providers():
    return config().get("providers", {}) or {}


def provider_for_issuer(issuer):
    """Return the provider entry whose ``issuer`` matches, or ``None``."""
    for entry in providers().values():
        if entry.get("issuer") == issuer:
            return entry
    return None


@functools.lru_cache(maxsize=None)
def _jwks_client(jwks_url):
    return PyJWKClient(jwks_url, cache_keys=True)


def jwks_client(provider):
    return _jwks_client(provider["jwks_url"])
