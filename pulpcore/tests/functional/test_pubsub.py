from types import SimpleNamespace
from datetime import datetime
import traceback
import select
import pytest
import sys
import os
from typing import NamedTuple
from functools import partial
from contextlib import contextmanager
from multiprocessing import Process, Pipe, Lock, SimpleQueue
from multiprocessing.connection import Connection


@pytest.fixture(autouse=True)
def django_connection_reset(django_db_blocker):
    # django_db_blocker is from pytest-django. We don't want it to try to safeguard
    # us from using our functional Pulp instance.
    # https://pytest-django.readthedocs.io/en/latest/database.html#django-db-blocker
    django_db_blocker.unblock()

    # If we dont' reset the connections we'll get interference between tests,
    # as listen/notify is connection based.
    from django.db import connections

    connections.close_all()
    yield
    django_db_blocker.block()


def test_postgres_pubsub():
    """Testing postgres low-level implementation."""
    from django.db import connection

    state = SimpleNamespace()
    state.got_message = False
    with connection.cursor() as cursor:
        assert connection.connection is cursor.connection
        conn = cursor.connection
        # Listen and Notify
        conn.execute("LISTEN abc")
        conn.add_notify_handler(lambda notification: setattr(state, "got_message", True))
        cursor.execute("NOTIFY abc, 'foo'")
        assert state.got_message is True
        conn.execute("SELECT 1")
        assert state.got_message is True

        # Reset and retry
        state.got_message = False
        conn.execute("UNLISTEN abc")
        cursor.execute("NOTIFY abc, 'foo'")
        assert state.got_message is False


class PubsubMessage(NamedTuple):
    channel: str
    payload: str


M = PubsubMessage


@pytest.fixture
def pubsub_backend(django_db_blocker):
    from pulpcore.tasking import pubsub

    return pubsub.PostgresPubSub


# @pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
class TestPublish:

    @pytest.mark.parametrize(
        "payload",
        (
            pytest.param(None, id="none"),
            pytest.param("", id="empty-string"),
            pytest.param("payload", id="non-empty-string"),
            pytest.param(123, id="int"),
            pytest.param(datetime.now(), id="datetime"),
            pytest.param(True, id="bool"),
        ),
    )
    def test_with_payload_as(self, pubsub_backend, payload):
        pubsub_backend.publish("channel", payload=payload)


# @pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
@pytest.mark.parametrize(
    "messages",
    (
        pytest.param([M("a", "A1")], id="single-message"),
        pytest.param([M("a", "A1"), M("a", "A2")], id="two-messages-in-same-channel"),
        pytest.param(
            [M("a", "A1"), M("a", "A2"), M("b", "B1"), M("c", "C1")],
            id="tree-msgs-in-different-channels",
        ),
    ),
)
class TestNoIpcSubscribeFetch:
    def unsubscribe_all(self, channels, subscriber):
        for channel in channels:
            subscriber.unsubscribe(channel)

    def subscribe_all(self, channels, subscriber):
        for channel in channels:
            subscriber.subscribe(channel)

    def publish_all(self, messages, publisher):
        for channel, payload in messages:
            publisher.publish(channel, payload=payload)

    def test_with(self, pubsub_backend, messages):
        channels = {m.channel for m in messages}
        publisher = pubsub_backend
        with pubsub_backend() as subscriber:
            self.subscribe_all(channels, subscriber)
            self.publish_all(messages, publisher)
            assert subscriber.fetch() == messages

            self.unsubscribe_all(channels, subscriber)
            assert subscriber.fetch() == []

    def test_select_readiness_with(self, pubsub_backend, messages):
        TIMEOUT = 0.1
        CHANNELS = {m.channel for m in messages}
        publisher = pubsub_backend
        with pubsub_backend() as subscriber:
            self.subscribe_all(CHANNELS, subscriber)
            assert subscriber.get_subscriptions() == CHANNELS

            ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber not in ready
            assert subscriber.fetch() == []

            self.publish_all(messages, publisher)
            ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber in ready

            ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber in ready
            assert subscriber.fetch() == messages

            ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber not in ready
            assert subscriber.fetch() == []

            self.unsubscribe_all(CHANNELS, subscriber)
            self.publish_all(messages, publisher)
            ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber not in ready
            assert subscriber.fetch() == []


class ProcessErrorData(NamedTuple):
    error: Exception
    stack_trace: str


class RemoteTracebackError(Exception):
    """An exception that wraps another exception and its remote traceback string."""

    def __init__(self, message, remote_traceback):
        super().__init__(message)
        self.remote_traceback = remote_traceback

    def __str__(self):
        """Override __str__ to include the remote traceback when printed."""
        return f"{super().__str__()}\n\n--- Remote Traceback ---\n{self.remote_traceback}"


class IpcUtil:

    @staticmethod
    def run(host_act, child_act) -> list:
        # ensures a connection from one run doesn't interfere with the other
        conn_1, conn_2 = Pipe()
        log = SimpleQueue()
        lock = Lock()
        turn_1 = partial(IpcUtil._actor_turn, conn_1, starts=True, log=log, lock=lock)
        turn_2 = partial(IpcUtil._actor_turn, conn_2, starts=False, log=log, lock=lock)
        proc_1 = Process(target=host_act, args=(turn_1, log))
        proc_2 = Process(target=child_act, args=(turn_2, log))
        proc_1.start()
        proc_2.start()
        try:
            proc_1.join()
        finally:
            conn_1.send("1")
        try:
            proc_2.join()
        finally:
            conn_2.send("1")
        conn_1.close()
        conn_2.close()
        result = IpcUtil.read_log(log)
        log.close()
        if proc_1.exitcode != 0 or proc_2.exitcode != 0:
            error = Exception("General exception")
            for item in result:
                if isinstance(item, ProcessErrorData):
                    error, stacktrace = item
                    break
            raise Exception(stacktrace) from error
        return result

    @staticmethod
    @contextmanager
    def _actor_turn(conn: Connection, starts: bool, log, lock: Lock, done: bool = False):
        TIMEOUT = 1

        try:

            def flush_conn(conn):
                if not conn.poll(TIMEOUT):
                    raise TimeoutError()
                conn.recv()

            if starts:
                with lock:
                    conn.send("done")
                    yield
                if not done:
                    flush_conn(conn)
            else:
                flush_conn(conn)
                with lock:
                    yield
                    conn.send("done")
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            err_header = f"Error from sub-process (pid={os.getpid()}) on test using IpcUtil"
            traceback_str = f"{err_header}\n\n{traceback.format_exc()}"

            error = ProcessErrorData(e, traceback_str)
            log.put(error)
            exit(1)

    @staticmethod
    def read_log(log: SimpleQueue) -> list:
        result = []
        while not log.empty():
            result.append(log.get())
        return result


def test_ipc_utils_error_catching():

    def host_act(host_turn, log):
        with host_turn():
            log.put(0)

    def child_act(child_turn, log):
        with child_turn():
            log.put(1)
            assert 1 == 0

    error_msg = "AssertionError: assert 1 == 0"
    with pytest.raises(Exception, match=error_msg):
        IpcUtil.run(host_act, child_act)


def test_ipc_utils_correctness():
    RUNS = 1000
    errors = 0

    def host_act(host_turn, log):
        with host_turn():
            log.put(0)

        with host_turn():
            log.put(2)

        with host_turn():
            log.put(4)

    def child_act(child_turn, log):
        with child_turn():
            log.put(1)

        with child_turn():
            log.put(3)

        with child_turn():
            log.put(5)

    def run():
        log = IpcUtil.run(host_act, child_act)
        if log != [0, 1, 2, 3, 4, 5]:
            return 1
        return 0

    for _ in range(RUNS):
        errors += run()

    error_rate = errors / RUNS
    assert error_rate == 0


def test_postgres_backend_ipc():
    """Asserts that we are really testing two different connections.

    From psycopg, the backend_id is:
    "The process ID (PID) of the backend process handling this connection."
    """
    from django.db import connection

    def host_act(host_turn, log):
        with host_turn():  # 1
            assert connection.connection is None
            with connection.cursor() as cursor:
                cursor.execute("select 1")
            assert connection.connection is not None
            log.put(connection.connection.info.backend_pid)

    def child_act(child_turn, log):
        with child_turn():  # 2
            assert connection.connection is None
            with connection.cursor() as cursor:
                cursor.execute("select 1")
            assert connection.connection is not None
            log.put(connection.connection.info.backend_pid)

    log = IpcUtil.run(host_act, child_act)
    assert len(log) == 2
    host_connection_pid, child_connection_pid = log
    assert host_connection_pid != child_connection_pid


# @pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
@pytest.mark.parametrize(
    "messages",
    (
        pytest.param([M("a", "A1")], id="single-message"),
        pytest.param([M("a", "A1")], id="test-leaking"),
        pytest.param([M("b", "B1"), M("b", "B2")], id="two-messages-in-same-channel"),
        pytest.param(
            [M("c", "C1"), M("c", "C2"), M("d", "D1"), M("d", "D1")],
            id="four-msgs-in-different-channels",
        ),
    ),
)
class TestIpcSubscribeFetch:

    def test_with(self, pubsub_backend, messages):
        CHANNELS = {m.channel for m in messages}
        EXPECTED_LOG = [
            "subscribe",
            "publish",
            "fetch",
            "publish",
            "fetch+unsubscribe",
            "publish",
            "fetch-empty",
        ]

        # host
        def subscriber_act(subscriber_turn, log):
            with pubsub_backend() as subscriber:
                with subscriber_turn():  # 1
                    log.put("subscribe")
                    for channel in CHANNELS:
                        subscriber.subscribe(channel)

                with subscriber_turn():  # 3
                    log.put("fetch")
                    assert subscriber.get_subscriptions() == CHANNELS
                    assert subscriber.fetch() == messages
                    assert subscriber.fetch() == []

                with subscriber_turn():  # 5
                    log.put("fetch+unsubscribe")
                    assert subscriber.fetch() == messages
                    assert subscriber.fetch() == []
                    for channel in CHANNELS:
                        subscriber.unsubscribe(channel)

                with subscriber_turn(done=True):  # 7
                    log.put("fetch-empty")
                    assert subscriber.fetch() == []

        # child
        def publisher_act(publisher_turn, log):
            publisher = pubsub_backend
            with publisher_turn():
                log.put("publish")
                for message in messages:  # 2
                    publisher.publish(message.channel, payload=message.payload)

            with publisher_turn():
                log.put("publish")
                for message in messages:  # 4
                    publisher.publish(message.channel, payload=message.payload)

            with publisher_turn():
                log.put("publish")
                for message in messages:  # 6
                    publisher.publish(message.channel, payload=message.payload)

        log = IpcUtil.run(subscriber_act, publisher_act)
        assert log == EXPECTED_LOG

    def test_select_readiness_with(self, pubsub_backend, messages):
        TIMEOUT = 0.1
        CHANNELS = {m.channel for m in messages}
        EXPECTED_LOG = [
            "subscribe/select-empty",
            "publish",
            "fetch/select-ready/unsubscribe",
            "publish",
            "fetch/select-empty",
        ]

        def subscriber_act(subscriber_turn, log):
            with pubsub_backend() as subscriber:
                with subscriber_turn():  # 1
                    log.put("subscribe/select-empty")
                    for channel in CHANNELS:
                        subscriber.subscribe(channel)
                    assert subscriber.get_subscriptions() == CHANNELS
                    ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
                    assert subscriber not in ready
                    assert subscriber.fetch() == []

                with subscriber_turn():  # 3
                    log.put("fetch/select-ready/unsubscribe")
                    ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
                    assert subscriber in ready

                    ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
                    assert subscriber in ready
                    assert subscriber.fetch() == messages
                    assert subscriber.fetch() == []
                    for channel in CHANNELS:
                        subscriber.unsubscribe(channel)

                with subscriber_turn():  # 5
                    log.put("fetch/select-empty")
                    ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
                    assert subscriber not in ready
                    assert subscriber.fetch() == messages

        def publisher_act(publisher_turn, log):
            publisher = pubsub_backend
            with publisher_turn():  # 2
                log.put("publish")
                for message in messages:
                    publisher.publish(message.channel, payload=message.payload)

            with publisher_turn():  # 4
                log.put("publish")
                for message in messages:
                    publisher.publish(message.channel, payload=message.payload)

        log = IpcUtil.run(subscriber_act, publisher_act)
        assert log == EXPECTED_LOG
