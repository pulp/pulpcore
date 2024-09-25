import atexit
import logging
import socket
from threading import Thread
from typing import Optional


from django.conf import settings


_bootstrap_servers = settings.get("KAFKA_BOOTSTRAP_SERVERS")


if _bootstrap_servers is None:

    def send_task_notification(task):
        pass

else:
    from confluent_kafka import Producer

    # NOTE: in spite of the name, cloudevents.http.CloudEvent is appropriate for other protocols
    from cloudevents.http import CloudEvent
    from cloudevents.kafka import to_structured
    from pulpcore.app.serializers.task import TaskStatusMessageSerializer

    _logger = logging.getLogger(__name__)
    _kafka_producer = None
    _producer_poll_timeout = settings.get("KAFKA_PRODUCER_POLL_TIMEOUT")
    _security_protocol = settings.get("KAFKA_SECURITY_PROTOCOL")
    _ssl_ca_pem = settings.get("KAFKA_SSL_CA_PEM")
    _sasl_mechanism = settings.get("KAFKA_SASL_MECHANISM")
    _sasl_username = settings.get("KAFKA_SASL_USERNAME")
    _sasl_password = settings.get("KAFKA_SASL_PASSWORD")

    _kafka_tasks_status_topic = settings.get("KAFKA_TASKS_STATUS_TOPIC")
    _kafka_tasks_status_producer_sync_enabled = settings.get(
        "KAFKA_TASKS_STATUS_PRODUCER_SYNC_ENABLED"
    )

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

    def _get_kafka_producer() -> Optional[Producer]:
        global _kafka_producer
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

    def _report_message_delivery(error, message):
        if error is not None:
            _logger.error(error)
        elif _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(f"Message delivery successfully with contents {message.value}")

    def send_task_notification(task):
        kafka_producer = _get_kafka_producer()
        attributes = {
            "type": "pulpcore.tasking.status",
            "source": "pulpcore.tasking",
            "datacontenttype": "application/json",
            "dataref": "https://github.com/pulp/pulpcore/blob/main/docs/static/task-status-v1.yaml",
        }
        data = TaskStatusMessageSerializer(task, context={"request": None}).data
        task_message = to_structured(CloudEvent(attributes, data))
        kafka_producer.produce(
            topic=_kafka_tasks_status_topic,
            value=task_message.value,
            key=task_message.key,
            headers=task_message.headers,
            on_delivery=_report_message_delivery,
        )
        if _kafka_tasks_status_producer_sync_enabled:
            kafka_producer.flush()
