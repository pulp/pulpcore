from typing import NamedTuple
import os
import logging
from contextlib import suppress

logger = logging.getLogger(__name__)


def wakeup_worker(pubsub_backend, reason="unknown"):
    pubsub_backend.publish(BasePubSubBackend.WORKER_WAKEUP, reason)


def cancel_task(task_pk, pubsub_backend):
    pubsub_backend.publish(BasePubSubBackend.TASK_CANCELLATION, str(task_pk))


def record_worker_metrics(pubsub_backend, now):
    pubsub_backend.publish(BasePubSubBackend.WORKER_METRIC, str(now))


class BasePubSubBackend:
    WORKER_WAKEUP = "pulp_worker_wakeup"
    TASK_CANCELLATION = "pulp_worker_cancel"
    WORKER_METRIC = "pulp_worker_metrics_heartbeat"

    def subscribe(self, channel, callback):
        raise NotImplementedError()

    def unsubscribe(self, channel):
        raise NotImplementedError()

    def publish(self, channel, message=None):
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

    def __init__(self, connection):
        self.cursor = connection.cursor()
        self.connection = connection.connection
        assert self.cursor.connection is self.connection
        self.subscriptions = []
        self.message_buffer = []
        self.connection.add_notify_handler(self._store_messages)
        # Handle message readiness
        # We can use os.evenfd in python >= 3.10
        self.sentinel_r, self.sentinel_w = os.pipe()
        os.set_blocking(self.sentinel_r, False)
        os.set_blocking(self.sentinel_w, False)
        logger.debug(f"Initialized pubsub. Conn={self.connection}")

    def _store_messages(self, notification):
        self.message_buffer.append(
            PubsubMessage(channel=notification.channel, payload=notification.payload)
        )

    def subscribe(self, channel):
        self.subscriptions.append(channel)
        self.connection.execute(f"LISTEN {channel}")

    def unsubscribe(self, channel):
        self.subscriptions.remove(channel)
        for i in range(0, len(self.message_buffer), -1):
            if self.message_buffer[i].channel == channel:
                self.message_buffer.pop(i)
        self.connection.execute(f"UNLISTEN {channel}")

    def publish(self, channel, message=None):
        if not message:
            self.cursor.execute(f"NOTIFY {channel}")
        else:
            self.cursor.execute("SELECT pg_notify(%s, %s)", (channel, message))

    def fileno(self) -> int:
        if self.message_buffer:
            os.write(self.sentinel_w, b"0")
        else:
            drain_non_blocking_fd(self.sentinel_r)
        return self.sentinel_r

    def fetch(self) -> list[PubsubMessage]:
        self.connection.execute("SELECT 1").fetchone()
        result = self.message_buffer.copy()
        self.message_buffer.clear()
        return result

    def close(self):
        os.close(self.sentinel_r)
        os.close(self.sentinel_w)
        self.cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
