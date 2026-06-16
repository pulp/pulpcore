from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from asgiref.sync import sync_to_async
from django_guid import clear_guid, get_guid, set_guid

from pulpcore.app.settings import REST_FRAMEWORK

_current_task = ContextVar("current_task", default=None)
_current_user_func = ContextVar("current_user", default=lambda: None)
_current_domain = ContextVar("current_domain", default=None)
x_task_diagnostics_var = ContextVar("x_profile_task")
_current_pulp_version = ContextVar(
    "current_pulp_version", default=REST_FRAMEWORK.get("DEFAULT_VERSION", "v3")
)


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
def with_task_context(task):
    with with_domain(task.pulp_domain), with_guid(task.logging_cid), with_user(task.user):
        task_token = _current_task.set(task)
        if not task.version:
            vers_token = _current_pulp_version.set(REST_FRAMEWORK.get("DEFAULT_VERSION", "v3"))
        else:
            vers_token = _current_pulp_version.set(task.version)

        # If this task is being spawned by another task, we should inherit the profile options
        # from the current task.
        diagnostics_token = x_task_diagnostics_var.set(task.profile_options)
        try:
            yield
        finally:
            x_task_diagnostics_var.reset(diagnostics_token)
            _current_task.reset(task_token)
            _current_pulp_version.reset(vers_token)


@asynccontextmanager
async def awith_task_context(task):
    @sync_to_async
    def _fetch(task):
        return task.pulp_domain, task.user

    domain, user = await _fetch(task)
    with with_domain(domain), with_guid(task.logging_cid), with_user(user):
        task_token = _current_task.set(task)
        if not task.version:
            vers_token = _current_pulp_version.set(REST_FRAMEWORK.get("DEFAULT_VERSION", "v3"))
        else:
            vers_token = _current_pulp_version.set(task.version)
        # If this task is being spawned by another task, we should inherit the profile options
        # from the current task.
        diagnostics_token = x_task_diagnostics_var.set(task.profile_options)
        try:
            yield
        finally:
            x_task_diagnostics_var.reset(diagnostics_token)
            _current_task.reset(task_token)
            _current_pulp_version.reset(vers_token)
