from django.db import connection
from pulpcore.tasking import pubsub
from types import SimpleNamespace
from datetime import datetime
import select
import pytest


def test_postgres_pubsub():
    """Testing postgres low-level implementation."""
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
    pytest.param(pubsub.PostgresPubSub, id="and-using-postgres-backend"),
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
    def test_with_payload_as(self, pubsub_backend, payload):
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
class TestSubscribeFetch:
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
        channels = {m.channel for m in messages}
        publisher = pubsub_backend
        with pubsub_backend() as subscriber:
            self.subscribe_all(channels, subscriber)
            r, w, x = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber not in r
            assert subscriber.fetch() == []

            self.publish_all(messages, publisher)
            r, w, x = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber in r
            assert subscriber.fetch() == messages
            assert subscriber.fetch() == []

            self.unsubscribe_all(channels, subscriber)
            self.publish_all(messages, publisher)
            r, w, x = select.select([subscriber], [], [], TIMEOUT)
            assert subscriber not in r
            assert subscriber.fetch() == []
