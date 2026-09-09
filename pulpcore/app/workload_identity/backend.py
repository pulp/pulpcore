"""A Django authentication backend that resolves permissions for a workload-identity principal.

Permission checks on a `WorkloadIdentityPrincipal` are answered here, from the per-request
grants carried on the principal, so the feature plugs into the normal `AUTHENTICATION_BACKENDS`
machinery. For any other user this backend defers by returning nothing.
"""

from django.contrib.auth.backends import BaseBackend

from pulpcore.app.workload_identity.authz import has_grant_perm, permissions_for
from pulpcore.app.workload_identity.principal import WorkloadIdentityPrincipal


class WorkloadIdentityBackend(BaseBackend):
    @staticmethod
    def _grants(user_obj):
        if isinstance(user_obj, WorkloadIdentityPrincipal):
            return user_obj.grants
        return None

    def has_perm(self, user_obj, perm, obj=None):
        grants = self._grants(user_obj)
        if grants is None:
            return False
        return has_grant_perm(grants, perm, obj)

    def has_module_perms(self, user_obj, app_label):
        # BaseBackend has no has_module_perms, so we provide it (mirrors ModelBackend).
        if self._grants(user_obj) is None:
            return False
        prefix = f"{app_label}."
        return any(perm.startswith(prefix) for perm in self.get_all_permissions(user_obj))

    def get_all_permissions(self, user_obj, obj=None):
        grants = self._grants(user_obj)
        if grants is None:
            return set()
        perms = permissions_for(grants, obj)
        if obj is None:
            return perms
        # Object-level checks report bare codenames, the convention Pulp's other backend uses.
        return {perm.split(".", 1)[1] for perm in perms}
