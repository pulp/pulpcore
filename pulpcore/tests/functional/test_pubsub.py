from types import SimpleNamespace
from datetime import datetime
import select
import pytest
from pulpcore.tasking import pubsub
from pulpcore.tests.functional.utils import IpcUtil


@pytest.fixture(autouse=True)
def django_connection_reset(request):
    # django_db_blocker is from pytest-django. We don't want it to try to safeguard
    # us from using our functional Pulp instance.
    # https://pytest-django.readthedocs.io/en/latest/database.html#django-db-blocker
    pytest_django_installed = False
    try:
        django_db_blocker = request.getfixturevalue("django_db_blocker")
        django_db_blocker.unblock()
        pytest_django_installed = True
    except pytest.FixtureLookupError:
        pass

    # If we dont' reset the connections we'll get interference between tests,
    # as listen/notify is connection based.
    from django.db import connections

    connections.close_all()
    yield
    if pytest_django_installed:
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


M = pubsub.PubsubMessage
PUBSUB_BACKENDS = [
    pubsub.PostgresPubSub,
]


@pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
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
    def test_with_payload_as(self, pubsub_backend: pubsub.BasePubSubBackend, payload):
        pubsub_backend.publish("channel", payload=payload)


@pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
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

    def test_with(
        self, pubsub_backend: pubsub.BasePubSubBackend, messages: list[pubsub.PubsubMessage]
    ):
        channels = {m.channel for m in messages}
        publisher = pubsub_backend
        with pubsub_backend() as subscriber:
            self.subscribe_all(channels, subscriber)
            self.publish_all(messages, publisher)
            assert subscriber.fetch() == messages

            self.unsubscribe_all(channels, subscriber)
            assert subscriber.fetch() == []

    def test_select_readiness_with(
        self, pubsub_backend: pubsub.BasePubSubBackend, messages: list[pubsub.PubsubMessage]
    ):
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


@pytest.mark.parametrize("pubsub_backend", PUBSUB_BACKENDS)
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

    def test_with(
        self, pubsub_backend: pubsub.BasePubSubBackend, messages: list[pubsub.PubsubMessage]
    ):
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

    def test_select_readiness_with(
        self, pubsub_backend: pubsub.BasePubSubBackend, messages: list[pubsub.PubsubMessage]
    ):
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

                with subscriber_turn(done=True):  # 5
                    log.put("fetch/select-empty")
                    ready, _, _ = select.select([subscriber], [], [], TIMEOUT)
                    assert subscriber not in ready
                    assert subscriber.fetch() == []

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
