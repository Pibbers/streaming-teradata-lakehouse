from __future__ import annotations

from confluent_kafka import Producer
import structlog

log = structlog.get_logger()


class KafkaPublisher:
    def __init__(self, bootstrap: str, client_id: str, acks: str = "all") -> None:
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap,
                "client.id": client_id,
                "acks": acks,
                # good defaults for local reliability
                "enable.idempotence": True,
                "linger.ms": 20,
                "batch.num.messages": 10000,
            }
        )

    def publish(self, topic: str, key: str, value: bytes) -> None:
        def delivery_report(err, msg):
            if err is not None:
                log.error("kafka_delivery_failed", error=str(err))
            else:
                log.debug(
                    "kafka_delivered",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )

        self._producer.produce(topic=topic, key=key, value=value, on_delivery=delivery_report)
        self._producer.poll(0)  # trigger delivery callbacks

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)