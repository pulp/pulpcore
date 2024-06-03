import atexit
import logging
import socket
from threading import Thread
from typing import Optional

from confluent_kafka import Producer
from django.conf import settings

_logger = logging.getLogger(__name__)
_kafka_producer = None
_bootstrap_servers = settings.get("KAFKA_BOOTSTRAP_SERVERS")
_producer_poll_timeout = settings.get("KAFKA_PRODUCER_POLL_TIMEOUT")
_security_protocol = settings.get("KAFKA_SECURITY_PROTOCOL")
_ssl_ca_pem = settings.get("KAFKA_SSL_CA_PEM")
_sasl_mechanism = settings.get("KAFKA_SASL_MECHANISM")
_sasl_username = settings.get("KAFKA_SASL_USERNAME")
_sasl_password = settings.get("KAFKA_SASL_PASSWORD")


class KafkaProducerPollingWorker:
    def __init__(self, kafka_producer):
        self._kafka_producer = kafka_producer
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = Thread(target=self._run)
        self._thread.start()

    def _run(self):
        while self._running:
            self._kafka_producer.poll(_producer_poll_timeout)
        self._kafka_producer.flush()

    def stop(self):
        self._running = False
        self._thread.join()


def get_kafka_producer() -> Optional[Producer]:
    global _kafka_producer
    if _bootstrap_servers is None:
        return None
    if _kafka_producer is None:
        conf = {
            "bootstrap.servers": _bootstrap_servers,
            "security.protocol": _security_protocol,
            "client.id": socket.gethostname(),
        }
        optional_conf = {
            "ssl.ca.pem": _ssl_ca_pem,
            "sasl.mechanisms": _sasl_mechanism,
            "sasl.username": _sasl_username,
            "sasl.password": _sasl_password,
        }
        for key, value in optional_conf.items():
            if value:
                conf[key] = value
        _kafka_producer = Producer(conf, logger=_logger)
        polling_worker = KafkaProducerPollingWorker(_kafka_producer)
        polling_worker.start()
        atexit.register(polling_worker.stop)
    return _kafka_producer
