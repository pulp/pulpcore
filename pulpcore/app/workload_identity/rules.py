"""Match token claims against the provider rules and collect the grants they earn.

Nothing here touches the database. A grant is `{"role": <name>, "scope": {...}}`.
"""

import fnmatch

from pulpcore.app.workload_identity.config import strategy


def _matches(match_spec, claims):
    """All claim conditions must match (AND). Values support `*` globbing."""
    for claim, pattern in match_spec.items():
        value = claims.get(claim)
        if value is None or not fnmatch.fnmatchcase(str(value), str(pattern)):
            return False
    return True


def grants_for(provider, claims):
    """Return the list of grants the claims earn for this provider.

    `strategy` "union" accumulates every matching rule; "first-match" stops at the first.
    """
    grants = []
    first_match = strategy() == "first-match"
    for rule in provider.get("rules", []):
        if _matches(rule.get("match", {}), claims):
            grants.extend(rule.get("grants", []))
            if first_match:
                break
    return grants
