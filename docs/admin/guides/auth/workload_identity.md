# Workload Identity Authentication

A CI job can authenticate to Pulp with a short-lived OIDC token from a third-party provider (for example GitHub Actions),
instead of a stored username and password.
The token is verified against the provider's public keys,
its claims are matched against a set of rules,
and the request is granted roles for that request only.
No user is created and nothing is written to the role tables.

This suits supply-chain workflows where a pipeline pushes content
and you want its permissions scoped to specific repositories without long-lived secrets.

!!! note
    The token is an OIDC token,
    but this is unrelated to the user-facing SSO login covered in [Using external service](external.md).
    It identifies a workload, not a person.

## How it works

On each request the token is read from the `Authorization: Bearer` header.
The `iss` claim selects a configured provider,
the signature is verified against the provider's JWKS,
and `iss`, `aud` and `exp` are checked.
The remaining claims are matched against the provider's rules to compute the roles and scopes for the request.
A token that matches no rule is rejected with a 401.

## Enabling

Add the authentication class to `DEFAULT_AUTHENTICATION_CLASSES`,
then populate `WORKLOAD_IDENTITY`:

```python title="settings.py"
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "pulpcore.app.workload_identity.authentication.WorkloadIdentityAuthentication",
    "pulpcore.app.authentication.BasicAuthentication",
    "rest_framework.authentication.SessionAuthentication",
]
```

No change to `AUTHENTICATION_BACKENDS` is needed.
The feature stays off while `WORKLOAD_IDENTITY` is empty,
so adding the class alone changes nothing.

With the example below,
a push from the `main` branch of `my-org/app` is granted the `file.filerepository_owner` role on the repository named `prod`,
and nothing else.
See the configuration reference at the end for every option.

## Roles for asynchronous tasks

Operations that dispatch a task, such as a sync, return a task the client polls.
A workload identity request is not a database user,
so it is not automatically granted a role on the tasks it creates.
Grant a role carrying `core.view_task` when the CI needs to read its own tasks.

## Domains

When `DOMAIN_ENABLED` is on, scope an object grant to a single tenant:
use a `prn`, or add a `domain` to a `name` scope.
A bare `name` matches that name in every domain, which breaks the isolation between domains.
Pulp raises a startup check warning when a name scope is left unqualified while domains are enabled.

## Configuration reference

Every option of the `WORKLOAD_IDENTITY` setting, annotated:

```python title="settings.py"
WORKLOAD_IDENTITY = {
    # How matching rules combine.
    # "union" (default) collects the grants of every matching rule.
    # "first-match" stops at the first matching rule.
    "strategy": "union",

    # One entry per trusted provider. The key is a name for your own reference.
    "providers": {
        "github": {
            # Required. Expected "iss" claim. Selects the provider and is verified while decoding.
            "issuer": "https://token.actions.githubusercontent.com",

            # Required. URL of the provider's JWKS. Keys are fetched and cached.
            "jwks_url": "https://token.actions.githubusercontent.com/.well-known/jwks",

            # Required. Expected "aud" claim.
            "audience": "https://pulp.example.com",

            # Optional. Allowed signing algorithms. Default: ["RS256"].
            "algorithms": ["RS256"],

            # Rules are evaluated in order. Each maps claims to grants.
            "rules": [
                {
                    # Claim name to expected value. Values support "*" globbing.
                    # Every entry must match (AND). A missing claim never matches.
                    "match": {"repository": "my-org/app", "ref": "refs/heads/main"},

                    # Grants awarded when the rule matches.
                    "grants": [
                        {
                            # Required. Name of a role that already exists in Pulp.
                            # A role that does not exist confers no permission.
                            "role": "file.filerepository_owner",

                            # Required. Where the role applies. One of:
                            #   {"type": "global"}                                    everywhere
                            #   {"type": "domain", "domain": "<name>"}                every object in a domain
                            #   {"type": "object", "name": "<name>"}                  one object by name
                            #   {"type": "object", "name": "<name>", "domain": "<d>"} one object by name in a domain
                            #   {"type": "object", "prn": "<prn>"}                    one object by PRN (domain-safe)
                            # With DOMAIN_ENABLED, qualify a name scope with a domain (or use prn):
                            # a bare name otherwise matches that name in every domain.
                            "scope": {"type": "object", "name": "prod"},
                        },
                    ],
                },
            ],
        },
    },
}
```
