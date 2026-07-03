"""Shared authorization logic over a list of grants.

A grant is ``{"role": <role name>, "scope": {...}}``. Scope is one of:

* ``{"type": "global"}``
* ``{"type": "domain", "domain": "<name>"}``
* ``{"type": "object", "name": "<name>"}`` (or ``"prn"``)

This module is used both by the principal (single-object ``has_perm`` and the model-level
permission set) and by ``get_objects_for_user`` (list filtering). Roles are read from the
database to resolve their permissions; the grant assignment itself is never stored.
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
    return role.permissions.filter(
        content_type__app_label=app_label, codename=codename
    ).exists()


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
        checks = (("prn", "prn"), ("name", "name"))
        provided = [key for key, _ in checks if key in scope]
        if not provided:
            return False
        return all(str(getattr(obj, attr, None)) == str(scope[key]) for key, attr in checks if key in scope)
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


def permissions_for(grants):
    """The set of ``app_label.codename`` the grants confer, for model-level ``get_all_permissions``."""
    from pulpcore.app.models.role import Role

    names = {g.get("role") for g in grants if g.get("role")}
    perms = set()
    for role in Role.objects.filter(name__in=names).prefetch_related("permissions__content_type"):
        for perm in role.permissions.all():
            perms.add(f"{perm.content_type.app_label}.{perm.codename}")
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
                clause = Q(prn=scope["prn"])
            elif "name" in scope:
                clause = Q(name=scope["name"])
        if clause is not None:
            predicate = clause if predicate is None else (predicate | clause)

    if predicate is None:
        return queryset.none()
    return queryset.filter(predicate)
