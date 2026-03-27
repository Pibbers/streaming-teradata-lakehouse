#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP="${KAFKA_BOOTSTRAP:-kafka:9092}"

echo "Creating topics on ${BOOTSTRAP} ..."

kafka-topics --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
  --topic crypto.trades.v1 --partitions 3 --replication-factor 1

kafka-topics --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
  --topic crypto.trades.dlq.v1 --partitions 3 --replication-factor 1

kafka-topics --bootstrap-server "$BOOTSTRAP" --create --if-not-exists \
  --topic crypto.pipeline.audit.v1 --partitions 1 --replication-factor 1

echo "Done. Current topics:"
kafka-topics --bootstrap-server "$BOOTSTRAP" --list