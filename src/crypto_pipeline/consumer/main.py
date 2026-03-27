from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

import orjson
import polars as pl
import structlog
from confluent_kafka import Consumer, KafkaException, TopicPartition

from crypto_pipeline.config import load_settings
from crypto_pipeline.logging import setup_logging
from crypto_pipeline.consumer.writer_parquet import ParquetWriter
from crypto_pipeline.producer.publisher import KafkaPublisher
from crypto_pipeline.storage.layout import parquet_partition_path
from crypto_pipeline.utils.time import trade_partitions

log = structlog.get_logger()


def build_consumer(settings) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": os.getenv("KAFKA_CONSUMER_GROUP", "crypto-consumer"),
            "auto.offset.reset": os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest"),
            "enable.auto.commit": False,  # commit only after write
            "client.id": "crypto-consumer",
        }
    )


def to_dlq_payload(raw_value: bytes | None, error: str, max_bytes: int) -> bytes:
    raw_str = ""
    if raw_value:
        try:
            raw_str = raw_value.decode("utf-8", errors="replace")
        except Exception:
            raw_str = repr(raw_value)

    if len(raw_str.encode("utf-8", errors="ignore")) > max_bytes:
        raw_str = raw_str[: max_bytes // 2] + "...<truncated>"

    payload = {
        "schema_version": 1,
        "source": "crypto-consumer",
        "error": error,
        "raw": raw_str,
    }
    return orjson.dumps(payload)


def flush_batch(
    writer: ParquetWriter,
    records: list[dict[str, Any]],
    offsets_to_commit: list[TopicPartition],
    consumer: Consumer,
    parquet_root: str,
    parquet_subdir: str,
) -> None:
    if not records:
        return

    # Group by (pair, trade_date, hour) → one parquet per group per flush
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        pair = r["symbol"]  # event field name remains symbol
        trade_date, hour = trade_partitions(int(r["trade_ts"]))
        grouped[(pair, trade_date, hour)].append(r)

    files = 0
    rows = 0

    for (pair, trade_date, hour), recs in grouped.items():
        out_dir = parquet_partition_path(parquet_root, parquet_subdir, pair, trade_date, hour)
        df = pl.from_dicts(recs)
        out_path = writer.write(df, out_dir)
        files += 1
        rows += len(recs)

        log.info(
            "parquet_written",
            file=str(out_path),
            rows=len(recs),
            pair=pair,
            trade_date=trade_date,
            hour=hour,
        )

    # commit offsets only after successful writes
    consumer.commit(offsets=offsets_to_commit, asynchronous=False)
    log.info(
        "offsets_committed",
        partitions=[{"topic": tp.topic, "partition": tp.partition, "offset": tp.offset} for tp in offsets_to_commit],
        files=files,
        rows=rows,
    )


def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    parquet_root = os.getenv("PARQUET_ROOT", "s3://crypto-trades")
    parquet_subdir = os.getenv("PARQUET_TOPIC_SUBDIR", "trades")
    batch_size = int(os.getenv("BATCH_SIZE", "5000"))
    flush_seconds = int(os.getenv("FLUSH_SECONDS", "10"))
    dlq_max_bytes = int(os.getenv("DLQ_MAX_BYTES", "200000"))

    consumer = build_consumer(settings)
    consumer.subscribe([settings.kafka_topic_trades])

    # Reuse our KafkaPublisher for DLQ publishing (no WS here, just Kafka produce)
    dlq_publisher = KafkaPublisher(
        bootstrap=settings.kafka_bootstrap,
        client_id="crypto-consumer-dlq",
        acks="all",
    )

    s3_client = None
    s3_bucket = ""
    if parquet_root.startswith("s3://"):
        import boto3

        s3_bucket = parquet_root[len("s3://"):]
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
        )

    writer = ParquetWriter(parquet_root, parquet_subdir, s3_client=s3_client, s3_bucket=s3_bucket)

    records: list[dict[str, Any]] = []
    offsets_map: dict[tuple[str, int], int] = {}  # (topic, partition) -> last_offset+1
    last_flush = time.time()
    consumed = 0
    dlq_count = 0

    log.info(
        "consumer_starting",
        topic=settings.kafka_topic_trades,
        group=os.getenv("KAFKA_CONSUMER_GROUP", "crypto-consumer"),
        parquet_root=parquet_root,
        batch_size=batch_size,
        flush_seconds=flush_seconds,
        dlq_topic=settings.kafka_topic_dlq,
    )

    try:
        while True:
            msg = consumer.poll(1.0)
            now = time.time()

            if msg is None:
                if records and (now - last_flush >= flush_seconds):
                    offsets_to_commit = [
                        TopicPartition(topic=t, partition=p, offset=o)
                        for (t, p), o in offsets_map.items()
                    ]
                    flush_batch(writer, records, offsets_to_commit, consumer, parquet_root, parquet_subdir)
                    records = []
                    offsets_map = {}
                    last_flush = now
                continue

            if msg.error():
                raise KafkaException(msg.error())

            # Always track offsets for messages we successfully process (or explicitly DLQ)
            topic = msg.topic()
            partition = msg.partition()
            next_offset = msg.offset() + 1

            try:
                rec = orjson.loads(msg.value())
                # minimal required keys check (lightweight “validation”)
                for k in ("symbol", "trade_id", "trade_ts", "price", "qty"):
                    if k not in rec:
                        raise ValueError(f"missing_key:{k}")

                records.append(rec)
                offsets_map[(topic, partition)] = next_offset
                consumed += 1

            except Exception as e:
                dlq_count += 1
                # publish to DLQ and move on; still advance offsets
                payload = to_dlq_payload(msg.value(), error=str(e), max_bytes=dlq_max_bytes)
                dlq_publisher.publish(
                    topic=settings.kafka_topic_dlq,
                    key=f"{topic}:{partition}",
                    value=payload,
                )
                offsets_map[(topic, partition)] = next_offset
                log.warn("dlq_published", error=str(e), dlq_count=dlq_count)

            if len(records) >= batch_size or (now - last_flush >= flush_seconds):
                offsets_to_commit = [
                    TopicPartition(topic=t, partition=p, offset=o)
                    for (t, p), o in offsets_map.items()
                ]
                flush_batch(writer, records, offsets_to_commit, consumer, parquet_root, parquet_subdir)
                records = []
                offsets_map = {}
                last_flush = now

            if consumed and consumed % 2000 == 0:
                log.info("consumer_progress", consumed=consumed, dlq_count=dlq_count)

    finally:
        try:
            if records and offsets_map:
                offsets_to_commit = [
                    TopicPartition(topic=t, partition=p, offset=o)
                    for (t, p), o in offsets_map.items()
                ]
                flush_batch(writer, records, offsets_to_commit, consumer, parquet_root, parquet_subdir)
        except Exception as e:
            log.error("final_flush_failed", error=str(e))
        consumer.close()
        dlq_publisher.flush(5.0)


def main() -> None:
    run()


if __name__ == "__main__":
    main()