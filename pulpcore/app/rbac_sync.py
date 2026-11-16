"""Keep stub Users/Groups on satellites so database-local role grants satisfy their foreign keys.

Users and Groups are always read from 'default'. A satellite only needs a row with the same pk,
created on demand right before a grant referencing it is written there.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction

logger = logging.getLogger(__name__)


def satellite_aliases():
    return [alias for alias in settings.DATABASES if alias != "default"]


def _ensure_stub(model, name_field, pk, alias):
    if pk is None or alias == "default":
        return
    manager = model.objects.using(alias)
    if manager.filter(pk=pk).exists():
        return
    defaults = {name_field: f"pulp-{pk}"}
    if hasattr(model, "set_password"):
        defaults["password"] = make_password(None)
    manager.get_or_create(pk=pk, defaults=defaults)


def ensure_identities_on_alias(alias, user_ids=(), group_ids=()):
    """Create missing stub Users/Groups on `alias` for the given pks."""
    from pulpcore.app.models import Group

    User = get_user_model()
    for pk in user_ids:
        _ensure_stub(User, User.USERNAME_FIELD, pk, alias)
    for pk in group_ids:
        _ensure_stub(Group, "name", pk, alias)


def on_user_role_pre_save(sender, instance, using, raw=False, **kwargs):
    if not raw:
        ensure_identities_on_alias(using, user_ids=[instance.user_id])


def on_group_role_pre_save(sender, instance, using, raw=False, **kwargs):
    if not raw:
        ensure_identities_on_alias(using, group_ids=[instance.group_id])


def _remove_stubs_after_commit(model, pk, using):
    def remove():
        for alias in satellite_aliases():
            try:
                # Cascades to the grants referencing it on that alias.
                model.objects.using(alias).filter(pk=pk).delete()
            except Exception:
                logger.exception(
                    "Removing %s(pk=%s) from alias '%s' failed.", model.__name__, pk, alias
                )

    if using == "default":
        transaction.on_commit(remove, using=using)


def on_user_post_delete(sender, instance, using, **kwargs):
    _remove_stubs_after_commit(sender, instance.pk, using)


def on_group_post_delete(sender, instance, using, **kwargs):
    _remove_stubs_after_commit(sender, instance.pk, using)
