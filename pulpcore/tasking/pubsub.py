from typing import NamedTuple
from pulpcore.constants import TASK_PUBSUB
import os
import logging
import select
from django.db import connection
from contextlib import suppress

logger = logging.getLogger(__name__)


class BasePubSubBackend:
    # Utils
    @classmethod
    def wakeup_worker(cls, reason="unknown"):
        cls.publish(TASK_PUBSUB.WAKEUP_WORKER, reason)

    @classmethod
    def cancel_task(cls, task_pk):
        cls.publish(TASK_PUBSUB.CANCEL_TASK, str(task_pk))

    @classmethod
    def record_worker_metrics(cls, now):
        cls.publish(TASK_PUBSUB.WORKER_METRICS, str(now))

    # Interface
    def subscribe(self, channel):
        raise NotImplementedError()

    def unsubscribe(self, channel):
        raise NotImplementedError()

    def get_subscriptions(self):
        raise NotImplementedError()

    @classmethod
    def publish(cls, channel, payload=None):
        raise NotImplementedError()

    def fileno(self):
        """Add support for being used in select loop."""
        raise NotImplementedError()

    def fetch(self):
        """Fetch messages new message, if required."""
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()


class PubsubMessage(NamedTuple):
    channel: str
    payload: str


def drain_non_blocking_fd(fd):
    with suppress(BlockingIOError):
        while True:
            os.read(fd, 256)


class PostgresPubSub(BasePubSubBackend):
    PID = os.getpid()

    def __init__(self):
        self._subscriptions = set()
        self.message_buffer = []
        # ensures a connection is initialized
        with connection.cursor() as cursor:
            cursor.execute("select 1")
        self.backend_pid = connection.connection.info.backend_pid
        self.sentinel_r, self.sentinel_w = os.pipe()
        os.set_blocking(self.sentinel_r, False)
        os.set_blocking(self.sentinel_w, False)
        connection.connection.add_notify_handler(self._store_messages)

    @classmethod
    def _debug(cls, message):
        logger.debug(f"[{cls.PID}] {message}")

    def _store_messages(self, notification):
        self.message_buffer.append(
            PubsubMessage(channel=notification.channel, payload=notification.payload)
        )
        if notification.pid == self.backend_pid:
            os.write(self.sentinel_w, b"1")
        self._debug(f"Received message: {notification}")

    @classmethod
    def publish(cls, channel, payload=""):
        query = (
            (f"NOTIFY {channel}",)
            if not payload
            else ("SELECT pg_notify(%s, %s)", (channel, str(payload)))
        )

        with connection.cursor() as cursor:
            cursor.execute(*query)
        cls._debug(f"Sent message: ({channel}, {str(payload)})")

    def subscribe(self, channel):
        self._subscriptions.add(channel)
        with connection.cursor() as cursor:
            cursor.execute(f"LISTEN {channel}")

    def unsubscribe(self, channel):
        self._subscriptions.remove(channel)
        for i in range(0, len(self.message_buffer), -1):
            if self.message_buffer[i].channel == channel:
                self.message_buffer.pop(i)
        with connection.cursor() as cursor:
            cursor.execute(f"UNLISTEN {channel}")

    def get_subscriptions(self):
        return self._subscriptions.copy()

    def fileno(self) -> int:
        # when pub/sub clients are the same, the notification callback may be called
        # asynchronously, making select on connection miss new notifications
        ready, _, _ = select.select([self.sentinel_r], [], [], 0)
        if self.sentinel_r in ready:
            return self.sentinel_r
        return connection.connection.fileno()

    def fetch(self) -> list[PubsubMessage]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1").fetchone()
        result = self.message_buffer.copy()
        self.message_buffer.clear()
        drain_non_blocking_fd(self.sentinel_r)
        self._debug(f"Fetched messages: {result}")
        return result

    def close(self):
        self.message_buffer.clear()
        connection.connection.remove_notify_handler(self._store_messages)
        drain_non_blocking_fd(self.sentinel_r)
        os.close(self.sentinel_r)
        os.close(self.sentinel_w)
        for channel in self.get_subscriptions():
            self.unsubscribe(channel)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


backend = PostgresPubSub
