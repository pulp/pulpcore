from django.db import connection
from pulpcore.tasking import pubsub
from types import SimpleNamespace
import select
import pytest


def test_postgres_pubsub():
    state = SimpleNamespace()
    state.got_first_message = False
    state.got_second_message = False
    with connection.cursor() as cursor:
        assert connection.connection is cursor.connection
        conn = cursor.connection
        conn.execute("LISTEN abc")
        conn.add_notify_handler(lambda notification: setattr(state, "got_message", True))
        cursor.execute("NOTIFY abc, 'foo'")
        conn.execute("SELECT 1")
        conn.execute("UNLISTEN abc")
    assert state.got_message is True


M = pubsub.PubsubMessage


@pytest.mark.parametrize(
    "messages",
    (
        [M("channel_a", "A1")],
        [M("channel_a", "A1"), M("channel_a", "A2")],
        [M("channel_a", "A1"), M("channel_a", "A2"), M("channel_b", "B1"), M("channel_c", "C1")],
    ),
)
@pytest.mark.parametrize("same_client", (True, False), ids=("same-clients", "different-clients"))
class TestPubSub:

    def test_subscribe_publish_fetch(self, same_client, messages):
        """
        GIVEN a publisher and a subscriber (which may be the same)
        AND a queue of messages Q with mixed channels and payloads
        WHEN the subscriber subscribes to all the channels in Q
        AND the publisher publishes all the messages in Q
        THEN the subscriber fetch() call returns a queue equivalent to Q
        AND calling fetch() a second time returns an empty queue
        """
        # Given
        publisher = pubsub.PostgresPubSub(connection)
        subscriber = publisher if same_client else pubsub.PostgresPubSub(connection)

        # When
        for message in messages:
            subscriber.subscribe(message.channel)
        for message in messages:
            publisher.publish(message.channel, message=message.payload)

        # Then
        assert subscriber.fetch() == messages
        assert subscriber.fetch() == []

    def test_unsubscribe(self, same_client, messages):
        """
        GIVEN a publisher and a subscriber (which may be the same)
        AND a queue of messages Q with mixed channels and payloads
        WHEN the subscriber subscribes and unsubscribes to all the channels in Q
        AND the publisher publishes all the messages in Q
        THEN the subscriber fetch() call returns an empty queue
        """
        # Given
        publisher = pubsub.PostgresPubSub(connection)
        subscriber = publisher if same_client else pubsub.PostgresPubSub(connection)

        # When
        for message in messages:
            subscriber.subscribe(message.channel)
        for message in messages:
            subscriber.unsubscribe(message.channel)
        for message in messages:
            publisher.publish(message.channel, message=message.payload)

        # Then
        assert subscriber.fetch() == []

    def test_select_loop(self, same_client, messages):
        """
        GIVEN a publisher and a subscriber (which may be the same)
        AND a queue of messages Q with mixed channels and payloads
        AND the subscriber is subscribed to all the channels in Q
        WHEN the publisher has NOT published anything yet
        THEN the select loop won't detect the subscriber readiness
        AND the subscriber fetch() call returns an empty queue
        BUT WHEN the publisher does publish all messages in Q
        THEN the select loop detects the subscriber readiness
        AND the subscriber fetch() call returns a queue equivalent to Q
        """
        TIMEOUT = 0.1

        # Given
        publisher = pubsub.PostgresPubSub(connection)
        subscriber = publisher if same_client else pubsub.PostgresPubSub(connection)

        # When
        for message in messages:
            subscriber.subscribe(message.channel)
        r, w, x = select.select([subscriber], [], [], TIMEOUT)

        # Then
        assert subscriber not in r
        assert subscriber.fetch() == []

        # But When
        for message in messages:
            publisher.publish(message.channel, message=message.payload)
        r, w, x = select.select([subscriber], [], [], TIMEOUT)

        # Then
        assert subscriber in r
        assert subscriber.fetch() == messages
        assert subscriber.fetch() == []
