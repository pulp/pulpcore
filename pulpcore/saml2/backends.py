import sys
from logging import getLogger

from djangosaml2.backends import Saml2Backend

from pulpcore.app.models import Domain
from pulpcore.app.models.role import Role
from pulpcore.app.util import resolve_prn


_logger = getLogger(__name__)


def _parse_role_assignment(role_assignment):
    try:
        _logger.debug("Considering role-assignment '%s'.", role_assignment)
        # TODO Is '/' a good choice here?
        role_name, domain_name, obj_prn = role_assignment.split("/")  # ':' is used in PRNs
        role = Role.objects.get(name=role_name)
        domain = None if domain_name == "" else Domain.objects.get(name=domain_name)
        obj = None if obj_prn == "" else resolve_prn(obj_prn)
    except Exception as e:
        _logger.warning(
            "Could not sync role-assignment '%s' from saml2 attributes.",
            role_assignment,
            exc_info=sys.exc_info(),
        )
        return None
    return role, domain, obj


class PulpSaml2Backend(Saml2Backend):
    def _update_user(
        self, user, attributes: dict, attribute_mapping: dict, force_save: bool = False
    ):
        if "pulp_roles" in attributes:
            _logger.debug("Sync role assignments for user '%s'.", user.username)
            role_assignments = (
                item
                for item in map(_parse_role_assignment, attributes["pulp_roles"])
                if item is not None
            )

            if user.pk is not None:
                # Adjust roles for existing user.
                assignment_pks = []
                for role, domain, obj in role_assignments:
                    if obj is None:
                        content_type = None
                        obj_pk = None
                    else:
                        content_type = 1
                        obj_pk = obj.pk
                    user_role = user.object_roles.filter(
                        role=role, domain=domain, content_type=content_type, object_id=obj_pk
                    ).first()
                    if user_role is None:
                        user_role = user.object_roles.create(
                            role=role, domain=domain, content_object=obj
                        )
                        _logger.debug("Created.")
                    else:
                        _logger.debug("Found.")
                    assignment_pks.append(user_role.pk)
                user.object_roles.exclude(pk__in=assignment_pks).delete()
            else:
                user.save()
                _logger.debug("New user object; create all role assignments.")
                for role, domain, obj in role_assignments:
                    user.object_roles.create(role=role, domain=domain, content_object=obj)

        return super()._update_user(user, attributes, attribute_mapping, force_save)
