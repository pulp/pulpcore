from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar

from asgiref.sync import sync_to_async
from django_guid import get_guid, set_guid, clear_guid


_current_task = ContextVar("current_task", default=None)
_current_user_func = ContextVar("current_user", default=lambda: None)
_current_domain = ContextVar("current_domain", default=None)


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
        token = _current_task.set(task)
        try:
            yield
        finally:
            _current_task.reset(token)


@asynccontextmanager
async def awith_task_context(task):
    @sync_to_async
    def _fetch(task):
        return task.pulp_domain, task.user

    domain, user = await _fetch(task)
    with with_domain(domain), with_guid(task.logging_cid), with_user(user):
        token = _current_task.set(task)
        try:
            yield
        finally:
            _current_task.reset(token)
