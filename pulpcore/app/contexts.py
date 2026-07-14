from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from asgiref.sync import sync_to_async
from django_guid import clear_guid, get_guid, set_guid

_current_task = ContextVar("current_task", default=None)
_current_user_func = ContextVar("current_user", default=lambda: None)
_current_domain = ContextVar("current_domain", default=None)
x_task_diagnostics_var = ContextVar("x_profile_task")
#: Set for the duration of a `migrate` management command run to the alias being migrated (see
#: `pulpcore.app.management.commands.migrate` and `PulpDomainRouter._resolve_db`). Historical
#: ("frozen state") models used inside `RunPython` migrations pre-date the domain router and were
#: never written with an explicit `.using(...)`, so without this the router would silently pin
#: every control-plane query (and every unrouted data-plane query) to `"default"` regardless of
#: which `--database` a given `migrate` invocation actually targets.
_current_migration_alias = ContextVar("current_migration_alias", default=None)


@contextmanager
def with_user(user):
    token = _current_user_func.set(lambda: user)
    try:
        yield
    finally:
        _current_user_func.reset(token)


@contextmanager
def with_guid(guid):
    old_guid = get_guid
    set_guid(guid)
    try:
        yield
    finally:
        if old_guid is None:
            clear_guid()
        else:
            set_guid(old_guid)


@contextmanager
def with_domain(domain):
    token = _current_domain.set(domain)
    try:
        yield
    finally:
        _current_domain.reset(token)


@contextmanager
def with_migration_alias(alias):
    token = _current_migration_alias.set(alias)
    try:
        yield
    finally:
        _current_migration_alias.reset(token)


@contextmanager
def with_task_context(task):
    with with_domain(task.pulp_domain), with_guid(task.logging_cid), with_user(task.user):
        task_token = _current_task.set(task)
        # If this task is being spawned by another task, we should inherit the profile options
        # from the current task.
        diagnostics_token = x_task_diagnostics_var.set(task.profile_options)
        try:
            yield
        finally:
            x_task_diagnostics_var.reset(diagnostics_token)
            _current_task.reset(task_token)


@asynccontextmanager
async def awith_task_context(task):
    @sync_to_async
    def _fetch(task):
        return task.pulp_domain, task.user

    domain, user = await _fetch(task)
    with with_domain(domain), with_guid(task.logging_cid), with_user(user):
        task_token = _current_task.set(task)
        # If this task is being spawned by another task, we should inherit the profile options
        # from the current task.
        diagnostics_token = x_task_diagnostics_var.set(task.profile_options)
        try:
            yield
        finally:
            x_task_diagnostics_var.reset(diagnostics_token)
            _current_task.reset(task_token)
