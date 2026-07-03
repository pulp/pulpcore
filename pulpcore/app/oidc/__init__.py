"""OIDC authentication for CI clients.

A validated OIDC token becomes a stateless principal that carries grants computed per request
from the ``OIDC_AUTH`` setting. Nothing is written to the role tables.
"""
