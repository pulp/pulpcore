from typing import NamedTuple
from pulpcore.constants import TASK_PUBSUB
import os
import logging
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

    @staticmethod
    def publish(channel, payload=None):
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


PID = os.getpid()


class PostgresPubSub(BasePubSubBackend):

    def __init__(self):
        self.subscriptions = []
        self.message_buffer = []
        # Ensures a connection is established
        if not connection.connection:
            with connection.cursor():
                pass
        connection.connection.add_notify_handler(self._store_messages)
        # Handle message readiness
        # We can use os.evenfd in python >= 3.10
        self.sentinel_r, self.sentinel_w = os.pipe()
        os.set_blocking(self.sentinel_r, False)
        os.set_blocking(self.sentinel_w, False)

    def _store_messages(self, notification):
        logger.info(f"[{PID}] Received message: {notification}")
        os.write(self.sentinel_w, b"0")
        self.message_buffer.append(
            PubsubMessage(channel=notification.channel, payload=notification.payload)
        )

    def subscribe(self, channel):
        self.subscriptions.append(channel)
        with connection.cursor() as cursor:
            cursor.execute(f"LISTEN {channel}")

    def unsubscribe(self, channel):
        self.subscriptions.remove(channel)
        for i in range(0, len(self.message_buffer), -1):
            if self.message_buffer[i].channel == channel:
                self.message_buffer.pop(i)
        with connection.cursor() as cursor:
            cursor.execute(f"UNLISTEN {channel}")

    @staticmethod
    def publish(channel, payload=None):
        logger.info(f"[{PID}] Published message: ({channel}, {payload})")
        if not payload:
            with connection.cursor() as cursor:
                cursor.execute(f"NOTIFY {channel}")
        else:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_notify(%s, %s)", (channel, str(payload)))

    def fileno(self) -> int:
        return self.sentinel_r

    def fetch(self) -> list[PubsubMessage]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1").fetchone()
        result = self.message_buffer.copy()
        drain_non_blocking_fd(self.sentinel_r)
        self.message_buffer.clear()
        # logger.info(f"[{PID}] Fetched messages: {result}")
        return result

    def close(self):
        os.close(self.sentinel_r)
        os.close(self.sentinel_w)
        self.message_buffer.clear()
        connection.connection.remove_notify_handler(self._store_messages)
        for channel in self.subscriptions:
            self.unsubscribe(channel)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


backend = PostgresPubSub
