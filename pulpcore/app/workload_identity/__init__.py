"""Workload identity authentication for CI clients.

A short-lived OIDC token from a third-party provider (for example GitHub Actions) becomes a
stateless principal whose grants are computed per request from the `WORKLOAD_IDENTITY` setting.
"""
