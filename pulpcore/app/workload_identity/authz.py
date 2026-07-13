"""Shared authorization logic over a list of grants.

A grant is ``{"role": <role name>, "scope": {...}}``. Scope is one of:

* ``{"type": "global"}``
* ``{"type": "domain", "domain": "<name>"}``
* ``{"type": "object", "name": "<name>"}`` (or ``"prn"``)

Roles are read from the database to resolve their permissions; the grant assignment is never stored.
"""

from django.db.models import Q


def _split(permission):
    app_label, _, codename = permission.partition(".")
    return app_label, codename


def _role_has_perm(role_name, app_label, codename):
    from pulpcore.app.models.role import Role

    if not role_name:
        return False
    try:
        role = Role.objects.get(name=role_name)
    except Role.DoesNotExist:
        return False
    return role.permissions.filter(content_type__app_label=app_label, codename=codename).exists()


def _scope_matches(scope, obj):
    """Whether a scope applies to a single object (``obj`` may be ``None`` for model-level)."""
    from pulpcore.app.models import Domain

    stype = scope.get("type")
    if stype == "global":
        return True
    if obj is None:
        return False
    if stype == "domain":
        if isinstance(obj, Domain):
            return obj.name == scope.get("domain")
        domain = getattr(obj, "pulp_domain", None)
        return domain is not None and domain.name == scope.get("domain")
    if stype == "object":
        if "prn" not in scope and "name" not in scope:
            return False
        if "prn" in scope:
            from pulpcore.app.util import get_prn

            try:
                if get_prn(obj) != scope["prn"]:
                    return False
            except Exception:
                return False
        if "name" in scope and str(getattr(obj, "name", None)) != str(scope["name"]):
            return False
        return True
    return False


def has_grant_perm(grants, permission, obj=None):
    """True if any grant confers ``permission`` and its scope matches ``obj``."""
    app_label, codename = _split(permission)
    for grant in grants:
        if _role_has_perm(grant.get("role"), app_label, codename) and _scope_matches(
            grant.get("scope", {}), obj
        ):
            return True
    return False


def permissions_for(grants, obj=None):
    """The set of ``app_label.codename`` the grants confer, scoped to ``obj`` when given."""
    from pulpcore.app.models.role import Role

    names = {g.get("role") for g in grants if g.get("role")}
    if not names:
        return set()
    role_perms = {}
    for role in Role.objects.filter(name__in=names).prefetch_related("permissions__content_type"):
        role_perms[role.name] = {
            f"{perm.content_type.app_label}.{perm.codename}" for perm in role.permissions.all()
        }
    perms = set()
    for grant in grants:
        conferred = role_perms.get(grant.get("role"))
        if not conferred:
            continue
        if obj is not None and not _scope_matches(grant.get("scope", {}), obj):
            continue
        perms |= conferred
    return perms


def grants_queryset(grants, permission, queryset):
    """Return ``queryset`` filtered to the objects the grants allow for ``permission``."""
    app_label, codename = _split(permission)
    relevant = [g for g in grants if _role_has_perm(g.get("role"), app_label, codename)]
    if not relevant:
        return queryset.none()

    has_domain = hasattr(queryset.model, "pulp_domain")
    predicate = None
    for grant in relevant:
        scope = grant.get("scope", {})
        stype = scope.get("type")
        if stype == "global":
            return queryset
        clause = None
        if stype == "domain" and has_domain:
            clause = Q(pulp_domain__name=scope.get("domain"))
        elif stype == "object":
            if "prn" in scope:
                from pulpcore.app.util import extract_pk

                try:
                    clause = Q(pk=extract_pk(scope["prn"], only_prn=True))
                except Exception:
                    clause = None
            elif "name" in scope:
                clause = Q(name=scope["name"])
        if clause is not None:
            predicate = clause if predicate is None else (predicate | clause)

    if predicate is None:
        return queryset.none()
    return queryset.filter(predicate)
